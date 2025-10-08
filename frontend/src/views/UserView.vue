<template>
  <div class="user-view-container">
    <!-- 頂部狀態欄 -->
    <header class="user-header">
      <div class="room-info">
        <h2 v-if="sessionStore.currentRoom">{{ sessionStore.currentRoom.name }}</h2>
        <div class="connection-status">
          <span :class="['status-dot', { connected: sessionStore.isConnected }]"></span>
          {{ sessionStore.isConnected ? '已連線' : '連線中...' }}
        </div>
      </div>
      <div class="language-settings">
        <div class="lang-setting">
          <label>我的慣用語(個人字幕):</label>
          <select v-model="inputLang" @change="updateSettings">
            <option value="zh-TW">繁體中文</option>
            <option value="zh-CN">簡體中文</option>
            <option value="en">English</option>
            <option value="ja">日本語</option>
            <option value="ko">한국어</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
            <option value="it">Italiano</option>
            <option value="pt">Português</option>
            <option value="ru">Русский</option>
            <option value="ar">العربية</option>
            <option value="hi">हिन्दी</option>
            <option value="th">ไทย</option>
            <option value="vi">Tiếng Việt</option>
            <option value="my">မြန်မာ (緬甸文)</option>
            <option value="id">Bahasa Indonesia (印尼文)</option>
            <option value="ms">Bahasa Melayu (馬來文)</option>
            <option value="yue">廣東話</option>
          </select>
        </div>
        <div class="lang-setting">
          <label>主板顯示語言:</label>
          <select v-model="outputLang" @change="updateSettings">
            <option value="zh-TW">繁體中文</option>
            <option value="zh-CN">簡體中文</option>
            <option value="en">English</option>
            <option value="ja">日本語</option>
            <option value="ko">한국어</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
            <option value="it">Italiano</option>
            <option value="pt">Português</option>
            <option value="ru">Русский</option>
            <option value="ar">العربية</option>
            <option value="hi">हिन्दी</option>
            <option value="th">ไทย</option>
            <option value="vi">Tiếng Việt</option>
            <option value="my">မြန်မာ (緬甸文)</option>
            <option value="id">Bahasa Indonesia (印尼文)</option>
            <option value="ms">Bahasa Melayu (馬來文)</option>
            <option value="yue">廣東話</option>
          </select>
        </div>
      </div>
    </header>

    <!-- 主要字幕顯示區域 -->
    <main class="subtitle-main">
      <div class="subtitle-display">
        <div v-if="latestMessage" class="current-subtitle">
          <div class="subtitle-meta">
            <span class="speaker">{{ latestMessage.speakerName }}</span>
            <span class="lang-info">{{ latestMessage.sourceLang }} → {{ outputLang }}</span>
            <span class="timestamp">{{ formatTimestamp(latestMessage.timestamp) }}</span>
          </div>
          <div class="subtitle-text">{{ latestMessage.text }}</div>
        </div>
        <div v-else class="waiting-message">
          <div class="waiting-icon">👂</div>
          <p>等待其他人發言...</p>
          <div class="connection-info">
            <p>房間人數: {{ connectedUsers }}</p>
            <p>我的慣用語: {{ inputLang }}</p>
            <p>主板顯示: {{ outputLang }}</p>
          </div>
        </div>
      </div>
    </main>

    <!-- 底部語音輸入區域 -->
    <footer class="user-footer">
      <div class="voice-section">
        <!-- 語音輸入按鈕 -->
        <div class="voice-input-container">
          <button 
            @click="toggleRecording"
            :class="['voice-btn', { recording: isRecording }]"
            :disabled="!sessionStore.isConnected || isProcessing"
          >
            <span class="voice-icon">🎤</span>
            <span class="voice-text">{{ 
              isProcessing ? '處理中...' : 
              isRecording ? '點擊送出' : 
              '點擊錄音' 
            }}</span>
          </button>
        </div>
        
        <!-- 語音提示 -->
        <div class="voice-tips">
          <p>🎤 純語音模式</p>
          <p>點擊開始錄音，再點擊送出翻譯</p>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { authApi, roomApi, ingestApi } from '../api/http'
import { speechApi } from '../api/speech'
import type { Message } from '../stores/session'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()

// 響應式數據
const inputLang = ref('zh-TW')  // 我的慣用語(個人字幕語言)
const outputLang = ref('en')    // 主板顯示語言
const isRecording = ref(false)
const isProcessing = ref(false)
const ws = ref<WebSocket | null>(null)
const connectedUsers = ref(0)

// 錄音相關
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
const stream = ref<MediaStream | null>(null)

// 房間 ID
const roomId = ref<string>('')

// 計算屬性：獲取最新的個人字幕訊息
const latestMessage = computed(() => {
  const messages = sessionStore.personalSubtitles
  if (messages.length === 0) return null
  
  // 顯示最新的個人字幕（包含自己和他人的）
  return messages[messages.length - 1]
})

// 初始化
onMounted(async () => {
  // 載入認證資料
  sessionStore.loadAuth()
  
  // 處理房間 ID (從查詢參數獲取)
  const routeRoomId = route.query.roomId as string
  if (!routeRoomId) {
    alert('無效的房間連結')
    router.push('/')
    return
  }
  
  roomId.value = routeRoomId
  
  // 每次都進行新的匿名登入，確保每個分頁有不同的用戶ID
  await performGuestLogin()
  
  // 載入用戶語言設定
  loadUserSettings()
  
  // 載入房間資料並連線
  await loadRoom()
  await connectWebSocket()
})

onUnmounted(() => {
  disconnectWebSocket()
  fullCleanup()
})

// 監聽房間變化
watch(() => route.params.roomId, async (newRoomId) => {
  if (newRoomId && newRoomId !== roomId.value) {
    roomId.value = newRoomId as string
    await loadRoom()
    await connectWebSocket()
  }
})

// 匿名登入
async function performGuestLogin() {
  try {
    // 為了測試多用戶場景，每個頁面都創建新的用戶
    // 在生產環境中可能需要不同的邏輯
    console.log('🆕 為每個頁面創建新用戶（測試模式）')
    
    const userName = `用戶_${Math.random().toString(36).substr(2, 6)}`
    console.log(`👤 創建新用戶: ${userName}, 慣用語: ${inputLang.value}, 主板語言: ${outputLang.value}`)
    const response = await authApi.guestLogin(userName, inputLang.value, inputLang.value, outputLang.value)
    
    const userInfo = {
      id: response.user_id,
      displayName: response.display_name,
      preferredLang: response.preferred_lang,
      inputLang: response.input_lang,
      outputLang: response.output_lang
    }
    
    sessionStore.setAuth(userInfo, response.token)
    
    // 測試模式：不保存 session，每個頁面都是獨立用戶
    console.log(`✅ 用戶創建完成: ${userInfo.displayName} (${userInfo.id.substring(0, 8)}...)`)
  } catch (error) {
    console.error('Guest login failed:', error)
    alert('登入失敗，請重新整理頁面')
  }
}

// 載入房間資料
async function loadRoom() {
  if (!roomId.value) return
  
  try {
    const response = await roomApi.getRoom(roomId.value)
    sessionStore.setRoom({
      id: response.id,
      name: response.name,
      defaultBoardLang: response.default_board_lang,
      overrides: response.overrides
    })
  } catch (error) {
    console.error('Load room failed:', error)
    alert('載入房間失敗')
  }
}

// WebSocket 連線
async function connectWebSocket() {
  if (!sessionStore.user || !roomId.value) return
  
  disconnectWebSocket()
  
  try {
    // 自動檢測 WebSocket 地址：使用當前頁面的協議和主機
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = window.location.host
    const wsUrl = `${wsProtocol}//${wsHost}/ws?roomId=${roomId.value}&userId=${sessionStore.user.id}&token=${sessionStore.token}`
    ws.value = new WebSocket(wsUrl)
    
    ws.value.onopen = () => {
      console.log('User WebSocket connected')
      sessionStore.setWebSocket(ws.value)
    }
    
    ws.value.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        handleWebSocketMessage(message)
      } catch (error) {
        console.error('Parse WebSocket message failed:', error)
      }
    }
    
    ws.value.onclose = () => {
      console.log('User WebSocket disconnected')
      sessionStore.setWebSocket(null)
      
      // 自動重連
      setTimeout(() => {
        if (roomId.value && sessionStore.user) {
          connectWebSocket()
        }
      }, 3000)
    }
    
    ws.value.onerror = (error) => {
      console.error('User WebSocket error:', error)
    }
  } catch (error) {
    console.error('Connect WebSocket failed:', error)
  }
}

// 斷開 WebSocket
function disconnectWebSocket() {
  if (ws.value) {
    ws.value.close()
    ws.value = null
    sessionStore.setWebSocket(null)
  }
}

// 處理 WebSocket 訊息
function handleWebSocketMessage(message: any) {
  console.log('🔄 收到 WebSocket 訊息:', message)
  
  switch (message.type) {
    case 'board.post':
      // 用戶視圖不處理主板訊息，主板訊息是給Host看的
      console.log('📢 主板訊息(忽略):', message.text, `(${message.speakerName})`)
      // 不添加到 boardMessages，用戶只看個人字幕
      break
      
    case 'personal.subtitle':
      console.log('👤 個人字幕:', message.text, `(${message.speakerName})`, `[${message.sourceLang}→${message.targetLang}]`)
      // 個人字幕：使用我的慣用語顯示
      if (message.targetLang === inputLang.value) {
        sessionStore.addPersonalSubtitle({
          id: message.messageId,
          speakerId: message.speakerId || '',
          speakerName: message.speakerName || '',
          text: message.text,
          sourceLang: message.sourceLang,
          targetLang: message.targetLang,
          timestamp: message.timestamp,
          type: 'personal'
        })
      }
      break
      
    case 'connection.established':
      console.log('🎉 連線已建立:', message)
      break
      
    case 'user.connected':
      console.log('👋 用戶連線:', message.message, `(房間人數: ${message.userCount})`)
      connectedUsers.value = message.userCount
      break
      
    case 'user.disconnected':
      console.log('👋 用戶離開:', message.message, `(房間人數: ${message.userCount})`)
      connectedUsers.value = message.userCount
      break
      
    default:
      console.log('❓ 未知訊息類型:', message.type, message)
  }
}

// 文字輸入功能已移除，純語音模式

// 切換錄音狀態
async function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else {
    await startRecording()
  }
}

// 開始錄音
async function startRecording() {
  if (!sessionStore.isConnected || isProcessing.value) return
  
  try {
    console.log('🎤 請求麥克風權限...')
    
    // 請求麥克風權限
    stream.value = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 48000
      }
    })
    
    console.log('✅ 麥克風權限獲取成功')
    
    // 建立 MediaRecorder
    const mimeType = getSupportedMimeType()
    mediaRecorder.value = new MediaRecorder(stream.value, {
      mimeType: mimeType,
      audioBitsPerSecond: 128000
    })
    
    audioChunks.value = []
    
    mediaRecorder.value.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.value.push(event.data)
      }
    }
    
    mediaRecorder.value.onstop = async () => {
      await processRecording()
    }
    
    // 開始錄音
    mediaRecorder.value.start(100) // 每100ms收集一次數據
    isRecording.value = true
    console.log('🔴 開始錄音')
    
  } catch (error) {
    console.error('❌ 麥克風權限被拒絕:', error)
    alert(`無法使用麥克風: ${error.message}`)
    cleanup()
  }
}

// 停止錄音
function stopRecording() {
  if (mediaRecorder.value && isRecording.value) {
    console.log('⏹️ 停止錄音')
    mediaRecorder.value.stop()
    isRecording.value = false
  }
}

// 處理錄音
async function processRecording() {
  if (audioChunks.value.length === 0) {
    console.error('❌ 錄音資料為空')
    cleanup()
    return
  }
  
  try {
    isProcessing.value = true
    console.log('🔄 處理錄音資料...')
    
    // 合併音頻資料
    const mimeType = getSupportedMimeType()
    const audioBlob = new Blob(audioChunks.value, { type: mimeType })
    
    console.log(`📦 音頻資料大小: ${(audioBlob.size / 1024).toFixed(1)} KB`)
    
    // 上傳到後端進行語音轉文字
    await uploadAudio(audioBlob)
    
  } catch (error) {
    console.error('❌ 處理錄音失敗:', error)
    alert('語音處理失敗，請重試')
  } finally {
    isProcessing.value = false
    cleanup()
  }
}

// 上傳音頻
async function uploadAudio(audioBlob: Blob) {
  try {
    const result = await speechApi.upload(
      roomId.value, 
      audioBlob, 
      inputLang.value || 'zh-TW'
    )
    console.log('✅ 語音轉文字成功:', result)
  } catch (error) {
    console.error('語音轉文字失敗:', error)
    throw error
  }
}

// 獲取支援的 MIME 類型（優先使用Groq相容格式）
function getSupportedMimeType(): string {
  const types = [
    'audio/wav',           // Groq最佳支援
    'audio/mp4',           // Groq支援
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus'
  ]
  
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) {
      console.log(`🎤 使用音頻格式: ${type}`)
      return type
    }
  }
  
  console.log('🎤 使用預設音頻格式: audio/webm')
  return 'audio/webm'
}

// 獲取檔案副檔名
function getFileExtension(): string {
  const mimeType = getSupportedMimeType()
  if (mimeType.includes('wav')) return 'wav'
  if (mimeType.includes('mp4')) return 'm4a'
  if (mimeType.includes('webm')) return 'webm'
  if (mimeType.includes('ogg')) return 'ogg'
  return 'wav'
}

// 清理資源
function cleanup() {
  // 不要停止音頻軌道，保持麥克風權限活躍
  // 只清理錄音相關的資源
  mediaRecorder.value = null
  audioChunks.value = []
}

// 完全清理資源（僅在組件卸載時調用）
function fullCleanup() {
  if (stream.value) {
    stream.value.getTracks().forEach(track => track.stop())
    stream.value = null
  }
  cleanup()
}

// 載入用戶設定
function loadUserSettings() {
  // 優先使用 sessionStore 中的用戶語言設定（確保用戶隔離）
  if (sessionStore.user?.inputLang) {
    inputLang.value = sessionStore.user.inputLang
    console.log(`📝 從 session 載入慣用語設定: ${inputLang.value}`)
  }
  if (sessionStore.user?.outputLang) {
    outputLang.value = sessionStore.user.outputLang
    console.log(`📝 從 session 載入主板語言設定: ${outputLang.value}`)
  }
  
  // 如果 session 中沒有設定，才使用 localStorage 作為後備
  if (!sessionStore.user?.inputLang || !sessionStore.user?.outputLang) {
    const savedSettings = localStorage.getItem('userLanguageSettings')
    if (savedSettings) {
      const settings = JSON.parse(savedSettings)
      if (!sessionStore.user?.inputLang) {
        inputLang.value = settings.inputLang || 'zh-TW'
      }
      if (!sessionStore.user?.outputLang) {
        outputLang.value = settings.outputLang || 'en'
      }
      console.log(`📝 從 localStorage 載入語言設定後備`)
    }
  }
}

// 更新設定
async function updateSettings() {
  const settings = {
    inputLang: inputLang.value,
    outputLang: outputLang.value
  }
  localStorage.setItem('userLanguageSettings', JSON.stringify(settings))
  
  // 更新用戶語言設定到後端
  if (sessionStore.user && sessionStore.token) {
    try {
      console.log(`🔄 更新語言設定 - 慣用語: ${inputLang.value}, 主板: ${outputLang.value}`)
      
      const result = await speechApi.updateUserLangs(inputLang.value, outputLang.value)
      console.log(`✅ 語言設定已更新: 慣用語=${result.input_lang}, 主板=${result.output_lang}`)
      
      // 更新本地狀態，確保不會被其他用戶影響
      sessionStore.updateUserLangs(inputLang.value, outputLang.value)
    } catch (error) {
      console.error('❌ 更新語言設定錯誤:', error)
    }
  }
}

// 格式化時間戳
function formatTimestamp(timestamp: string | null) {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleTimeString()
}
</script>

<style scoped>
.user-view-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  overflow: hidden;
}

.user-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
}

.room-info h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  color: #666;
  margin-top: 0.25rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #dc3545;
  transition: background-color 0.3s;
}

.status-dot.connected {
  background: #28a745;
}

.language-settings {
  display: flex;
  gap: 1rem;
}

.lang-setting {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.lang-setting label {
  font-size: 0.8rem;
  color: #666;
}

.lang-setting select {
  padding: 0.25rem 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.9rem;
}

.subtitle-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.subtitle-display {
  width: 100%;
  max-width: 800px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  padding: 2rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.current-subtitle {
  animation: fadeIn 0.5s ease-in;
}

.subtitle-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  font-size: 0.9rem;
  color: #666;
}

.speaker {
  font-weight: 600;
  color: #333;
}

.lang-info {
  background: #007bff;
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.8rem;
}

.timestamp {
  font-size: 0.8rem;
  color: #999;
  font-style: italic;
}

.connection-info {
  margin-top: 1rem;
  font-size: 0.9rem;
  color: #666;
  text-align: center;
}

.connection-info p {
  margin: 0.25rem 0;
}

.subtitle-text {
  font-size: 2rem;
  line-height: 1.4;
  color: #333;
  font-weight: 500;
  min-height: 3rem;
}

.waiting-message {
  color: #888;
}

.waiting-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.waiting-message p {
  font-size: 1.2rem;
  margin: 0;
}

.user-footer {
  padding: 1.5rem;
  background: rgba(255, 255, 255, 0.9);
}

.voice-section {
  max-width: 600px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.voice-input-container {
  display: flex;
  justify-content: center;
}

.voice-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem 2rem;
  border: none;
  border-radius: 50px;
  background: #28a745;
  color: white;
  cursor: pointer;
  transition: all 0.3s;
  user-select: none;
  min-width: 120px;
  min-height: 80px;
}

.voice-btn:hover:not(:disabled) {
  background: #218838;
  transform: scale(1.05);
}

.voice-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
  transform: none;
}

.voice-btn.recording {
  background: linear-gradient(135deg, #ff4444, #cc0000);
  color: white;
  transform: scale(1.1);
  box-shadow: 0 0 20px rgba(255, 68, 68, 0.7);
  border: 3px solid #ff0000;
  animation: pulse 1s infinite;
}

.voice-icon {
  font-size: 1.5rem;
}

.voice-text {
  font-size: 0.9rem;
  font-weight: 500;
}

.voice-tips {
  text-align: center;
  color: #666;
  max-width: 400px;
}

.voice-tips p {
  margin: 0.25rem 0;
  font-size: 0.9rem;
}

.voice-tips p:first-child {
  font-weight: 600;
  color: #333;
  font-size: 1rem;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

/* Mobile responsive styles */
@media (max-width: 768px) {
  .user-view-container {
    height: 100vh;
    height: 100dvh; /* 使用動態視窗高度，避免手機瀏覽器地址欄問題 */
    overflow: hidden;
  }
  
  .user-header {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
    flex-shrink: 0;
  }
  
  .room-info {
    text-align: center;
    width: 100%;
  }
  
  .room-info h2 {
    font-size: 1.1rem;
  }
  
  .language-settings {
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
  }
  
  .lang-setting {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }
  
  .lang-setting label {
    font-size: 0.75rem;
    min-width: 120px;
  }
  
  .lang-setting select {
    flex: 1;
    margin-left: 0.5rem;
    font-size: 0.8rem;
  }
  
  .subtitle-main {
    padding: 1rem;
  }
  
  .subtitle-display {
    padding: 1.5rem;
    border-radius: 12px;
  }
  
  .subtitle-text {
    font-size: 1.5rem;
    min-height: 2rem;
  }
  
  .subtitle-meta {
    flex-direction: column;
    gap: 0.5rem;
    text-align: center;
  }
  
  .waiting-icon {
    font-size: 2rem;
  }
  
  .waiting-message p {
    font-size: 1rem;
  }
  
  .user-footer {
    padding: 1rem;
  }
  
  .voice-section {
    gap: 1rem;
  }
  
  .voice-btn {
    min-width: 140px;
    min-height: 100px;
    padding: 1.5rem;
  }
  
  .voice-icon {
    font-size: 2rem;
  }
  
  .voice-text {
    font-size: 1rem;
    font-weight: 600;
  }
  
  .voice-tips {
    max-width: 300px;
  }
  
  .voice-tips p {
    font-size: 0.8rem;
  }
  
  .voice-tips p:first-child {
    font-size: 0.9rem;
  }
}

@media (max-width: 480px) {
  .user-header {
    padding: 0.75rem;
  }
  
  .room-info h2 {
    font-size: 1rem;
  }
  
  .connection-status {
    font-size: 0.8rem;
  }
  
  .lang-setting label {
    font-size: 0.7rem;
    min-width: 100px;
  }
  
  .lang-setting select {
    font-size: 0.75rem;
  }
  
  .subtitle-main {
    padding: 0.75rem;
  }
  
  .subtitle-display {
    padding: 1rem;
  }
  
  .subtitle-text {
    font-size: 1.25rem;
  }
  
  .voice-btn {
    min-width: 120px;
    min-height: 90px;
    padding: 1rem;
  }
  
  .voice-icon {
    font-size: 1.8rem;
  }
  
  .voice-text {
    font-size: 0.9rem;
  }
  
  .user-footer {
    padding: 0.75rem;
  }
}
</style>