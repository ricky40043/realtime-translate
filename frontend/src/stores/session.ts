import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface User {
  id: string
  displayName: string
  preferredLang: string
  inputLang?: string
  outputLang?: string
}

export interface Room {
  id: string
  name: string
  defaultBoardLang: string
  overrides: Array<{ speakerId: string; targetLang: string }>
}

export interface Message {
  id: string
  speakerId: string
  speakerName: string
  text: string
  sourceLang: string
  targetLang: string
  timestamp: string
  type: 'personal' | 'board'
}

export const useSessionStore = defineStore('session', () => {
  // 使用者狀態
  const user = ref<User | null>(null)
  const token = ref<string | null>(null)
  
  // 房間狀態
  const currentRoom = ref<Room | null>(null)
  const isConnected = ref(false)
  
  // 訊息狀態
  const personalSubtitles = ref<Message[]>([])
  const boardMessages = ref<Message[]>([])
  
  // WebSocket 狀態
  const ws = ref<WebSocket | null>(null)
  
  // Computed
  const isAuthenticated = computed(() => user.value !== null && token.value !== null)
  const currentSubtitle = computed(() => 
    personalSubtitles.value.length > 0 ? personalSubtitles.value[personalSubtitles.value.length - 1] : null
  )
  
  // Actions
  function setAuth(userData: User, authToken: string) {
    user.value = userData
    token.value = authToken
    // 儲存到 localStorage
    localStorage.setItem('user', JSON.stringify(userData))
    localStorage.setItem('token', authToken)
  }
  
  function clearAuth() {
    user.value = null
    token.value = null
    localStorage.removeItem('user')
    localStorage.removeItem('token')
  }
  
  function loadAuth() {
    const savedUser = localStorage.getItem('user')
    const savedToken = localStorage.getItem('token')
    
    if (savedUser && savedToken) {
      user.value = JSON.parse(savedUser)
      token.value = savedToken
    }
  }
  
  function setRoom(room: Room) {
    currentRoom.value = room
  }
  
  function addPersonalSubtitle(message: Message) {
    personalSubtitles.value.push(message)
    // 保持最近 50 條字幕
    if (personalSubtitles.value.length > 50) {
      personalSubtitles.value = personalSubtitles.value.slice(-50)
    }
  }
  
  function addBoardMessage(message: Message) {
    boardMessages.value.push(message)
    // 保持最近 100 條訊息
    if (boardMessages.value.length > 100) {
      boardMessages.value = boardMessages.value.slice(-100)
    }
  }
  
  function clearMessages() {
    personalSubtitles.value = []
    boardMessages.value = []
  }
  
  function setWebSocket(websocket: WebSocket | null) {
    ws.value = websocket
    isConnected.value = websocket !== null
  }
  
  function updateUserLang(newLang: string) {
    if (user.value) {
      user.value.preferredLang = newLang
      localStorage.setItem('user', JSON.stringify(user.value))
    }
  }
  
  return {
    // State
    user,
    token,
    currentRoom,
    isConnected,
    personalSubtitles,
    boardMessages,
    ws,
    
    // Computed
    isAuthenticated,
    currentSubtitle,
    
    // Actions
    setAuth,
    clearAuth,
    loadAuth,
    setRoom,
    addPersonalSubtitle,
    addBoardMessage,
    clearMessages,
    setWebSocket,
    updateUserLang
  }
})