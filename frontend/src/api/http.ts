// 自動檢測 API 基礎地址：開發時使用 localhost，生產時使用當前主機
const API_BASE = `http://${window.location.hostname}:8081/api`
// const API_BASE = process.env.NODE_ENV === 'production' 
//   ? `http://${window.location.hostname}:8081/api`
//   : 'http://localhost:8081/api'

export interface ApiResponse<T = any> {
  data?: T
  error?: string
}

export class ApiError extends Error {
  public status: number
  
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token')
  
  const config: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers
    },
    ...options
  }
  const response = await fetch(`${API_BASE}${endpoint}`, config)
  
  if (!response.ok) {
    const errorText = await response.text()
    throw new ApiError(response.status, errorText || response.statusText)
  }
  
  return response.json()
}



// 認證 API
export const authApi = {
  async guestLogin(displayName: string, preferredLang: string = 'zh-TW', inputLang: string = '', outputLang: string = 'zh-TW') {
    return request<{
      user_id: string
      token: string
      display_name: string
      preferred_lang: string
      input_lang: string
      output_lang: string
    }>('/auth/guest', {
      method: 'POST',
      body: JSON.stringify({
        display_name: displayName,
        preferred_lang: preferredLang,
        input_lang: inputLang,
        output_lang: outputLang
      })
    })
  }
}

// 房間 API
export const roomApi = {
  async createRoom(name: string, defaultBoardLang: string = 'en') {
    return request<{
      id: string
      name: string
      default_board_lang: string
      created_at: string
    }>('/rooms', {
      method: 'POST',
      body: JSON.stringify({
        name,
        default_board_lang: defaultBoardLang
      })
    })
  },
  
  async getRoom(roomId: string) {
    return request<{
      id: string
      name: string
      default_board_lang: string
      created_at: string
      overrides: Array<{ speakerId: string; targetLang: string }>
    }>(`/rooms/${roomId}`)
  },
  
  async updateBoardLang(roomId: string, defaultBoardLang: string) {
    return request(`/rooms/${roomId}/board-lang`, {
      method: 'PUT',
      body: JSON.stringify({
        default_board_lang: defaultBoardLang
      })
    })
  },
  
  async updateOverrides(roomId: string, overrides: Array<{ speakerId: string; targetLang: string }>) {
    return request(`/rooms/${roomId}/overrides`, {
      method: 'PUT',
      body: JSON.stringify({ overrides })
    })
  },
  
  async updateUserLang(userId: string, preferredLang: string) {
    return request(`/rooms/users/${userId}/preferred-lang`, {
      method: 'PUT',
      body: JSON.stringify({
        preferred_lang: preferredLang
      })
    })
  }
}

// 訊息 API
export const ingestApi = {
  async sendText(roomId: string, text: string, sourceLang?: string, isFinal: boolean = true) {
    return request<{
      message_id: string
      source_lang: string
      status: string
    }>('/ingest/text', {
      method: 'POST',
      body: JSON.stringify({
        room_id: roomId,
        text,
        source_lang: sourceLang,
        is_final: isFinal
      })
    })
  }
}