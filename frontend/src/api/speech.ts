// 統一的 API 基礎地址
const API_BASE = '/api'

// 獲取認證 token
const getAuthToken = () => localStorage.getItem('token') || ''

// 統一的請求配置
const getAuthHeaders = () => ({
  'Authorization': `Bearer ${getAuthToken()}`
})

/**
 * 語音相關 API
 */
export const speechApi = {
  /**
   * 上傳語音文件進行處理
   */
  async upload(roomId: string, audioBlob: Blob, userLang?: string): Promise<any> {
    const formData = new FormData()
    formData.append('audio', audioBlob, 'audio.webm')
    formData.append('room_id', roomId)
    if (userLang) {
      formData.append('user_lang', userLang)
    }

    const response = await fetch(`${API_BASE}/speech/upload`, {
      method: 'POST',
      body: formData,
      headers: getAuthHeaders()
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Speech upload failed: ${error}`)
    }

    return response.json()
  },

  /**
   * 更新用戶語言設定
   */
  async updateUserLangs(inputLang: string, outputLang: string): Promise<any> {
    const response = await fetch(`${API_BASE}/auth/update-langs`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        input_lang: inputLang,
        output_lang: outputLang
      })
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Update user langs failed: ${error}`)
    }

    return response.json()
  }
}

/**
 * 分段語音處理 API
 */
export const speechStagedApi = {
  /**
   * 僅進行語音轉文字 (STT)
   */
  async sttOnly(roomId: string, audioBlob: Blob, userLang?: string): Promise<any> {
    const formData = new FormData()
    formData.append('audio', audioBlob, 'audio.webm')
    formData.append('room_id', roomId)
    if (userLang) {
      formData.append('user_lang', userLang)
    }

    const response = await fetch(`${API_BASE}/speech-staged/stt-only`, {
      method: 'POST',
      body: formData,
      headers: getAuthHeaders()
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`STT failed: ${error}`)
    }

    return response.json()
  },

  /**
   * 語音轉文字 + 翻譯（分段式）
   */
  async translateStt(transcriptId: string, roomId: string): Promise<any> {
    const response = await fetch(`${API_BASE}/speech-staged/translate-stt`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        transcript_id: transcriptId,
        room_id: roomId
      })
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Translate STT failed: ${error}`)
    }

    return response.json()
  },

  /**
   * 獲取轉錄結果
   */
  async getTranscript(messageId: string): Promise<any> {
    const response = await fetch(`${API_BASE}/speech-staged/transcript/${messageId}`, {
      method: 'GET',
      headers: getAuthHeaders()
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Get transcript failed: ${error}`)
    }

    return response.json()
  },

  /**
   * 刪除轉錄結果
   */
  async deleteTranscript(transcriptId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/speech-staged/transcript/${transcriptId}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Delete transcript failed: ${error}`)
    }
  }
}