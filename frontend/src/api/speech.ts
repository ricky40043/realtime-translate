// 統一的 API 基礎地址
const API_BASE = import.meta.env.VITE_API_URL || '/api'

// 獲取認證 token
const getAuthToken = () => localStorage.getItem('token') || ''

// 統一的請求配置
const getAuthHeaders = () => ({
  'Authorization': `Bearer ${getAuthToken()}`
})

export interface TranslatorResponse {
  transcript: string
  translated_text: string
  detected_lang: string
  source_lang: string
  target_lang: string
  confidence: number
  status?: 'ok' | 'empty' | 'other_lang'
  quota?: { speech: QuotaInfo | null; translate: QuotaInfo | null } | null
}

export interface QuotaInfo {
  remaining: number
  limit: number
}

/**
 * 語音相關 API
 */
export const speechApi = {
  /**
   * 雙向翻譯機：上傳一次錄音，由後端自動偵測兩種語言中的來源語言。
   */
  async translate(
    audioBlob: Blob,
    langA: string,
    langB: string,
    options: { isFinal?: boolean } = {}
  ): Promise<TranslatorResponse> {
    const formData = new FormData()
    const ext = audioBlob.type.includes('wav') ? 'wav' : audioBlob.type.includes('mp4') ? 'm4a' : audioBlob.type.includes('ogg') ? 'ogg' : 'webm'
    formData.append('audio', audioBlob, `translator.${ext}`)
    formData.append('lang_a', langA)
    formData.append('lang_b', langB)
    // 講話中的即時預覽 is_final=false；一句講完才送 true
    formData.append('is_final', String(options.isFinal ?? true))

    const response = await fetch(`${API_BASE}/translator/translate`, {
      method: 'POST',
      body: formData,
      headers: getAuthHeaders()
    })

    if (!response.ok) {
      let message = '翻譯失敗，請稍後再試'
      const errorText = await response.text()
      try {
        const error = JSON.parse(errorText)
        message = error.detail || message
      } catch {
        if (errorText) message = errorText
      }
      throw Object.assign(new Error(message), { status: response.status })
    }

    return response.json()
  },

  /**
   * Groq 今天剩餘的呼叫次數（語音辨識、翻譯）
   */
  async quota(): Promise<{ speech: QuotaInfo | null; translate: QuotaInfo | null }> {
    const response = await fetch(`${API_BASE}/translator/quota`, { headers: getAuthHeaders() })
    if (!response.ok) throw new Error('quota unavailable')
    return response.json()
  },

  /**
   * 上傳語音文件進行處理
   */
  async upload(
    roomId: string,
    audioBlob: Blob,
    userLang?: string,
    speakerName?: string,
    segment?: { utteranceId: string; window: number; isFinal: boolean }
  ): Promise<any> {
    const formData = new FormData()
    const ext = audioBlob.type.includes('wav') ? 'wav' : audioBlob.type.includes('mp4') ? 'm4a' : 'webm'
    formData.append('audio', audioBlob, `audio.${ext}`)
    formData.append('room_id', roomId)
    if (segment) {
      // 分段即時翻譯：同一句話共用 utterance_id，is_final=false 表示還沒講完
      formData.append('utterance_id', segment.utteranceId)
      formData.append('window', String(segment.window))
      formData.append('is_final', String(segment.isFinal))
    }
    if (userLang) {
      formData.append('language_code', userLang)
    }
    if (speakerName) {
      formData.append('speaker_name', speakerName)
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
