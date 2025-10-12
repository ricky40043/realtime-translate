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
      <div class="user-controls">
        <div class="user-info">
          <span class="user-name">{{ userSettings.displayName || '未設定' }}</span>
          <span class="lang-info">{{ getLanguageName(inputLang) }} → {{ getLanguageName(outputLang) }}</span>
        </div>
        <button @click="openSettings" class="settings-btn" title="個人設定">
          ⚙️
        </button>
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
        <!-- 智能語音錄音器 -->
        <SmartVoiceRecorder
          :room-id="roomId"
          :user-lang="inputLang"
          :settings="userSettings"
          :disabled="!sessionStore.isConnected"
          @transcript="handleTranscript"
          @error="handleVoiceError"
          @recording-start="handleRecordingStart"
          @recording-end="handleRecordingEnd"
        />
      </div>
    </footer>

    <!-- 設定Modal -->
    <SettingsModal
      :show="showSettingsModal"
      :initial-settings="userSettings"
      :is-first-time="isFirstTime"
      @close="closeSettingsModal"
      @save="saveUserSettings"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { authApi, roomApi, ingestApi } from '../api/http'
import { speechApi } from '../api/speech'
import type { Message } from '../stores/session'
import SettingsModal from '../components/SettingsModal.vue'
import SmartVoiceRecorder from '../components/SmartVoiceRecorder.vue'

interface AdvancedSettings {
  displayName: string
  inputLang: string
  outputLang: string
  segmentThreshold: number    // 語音檢測閾值（統一用於語音檢測和自動分段）
  silenceTimeout: number      // 靜音超時時間（多久沒聲音後結束錄音）
  minSegmentTime: number      // 最短分段時間
  segmentDelay: number        // 分段延遲時間（低於閾值後持續多久才送出）
  maxRecordingTime: number    // 最長連續錄音時間
}

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

// 設定Modal相關
const showSettingsModal = ref(false)
const isFirstTime = ref(false)
const userSettings = ref<AdvancedSettings>({
  displayName: '',
  inputLang: 'zh-TW',
  outputLang: 'zh-TW',
  segmentThreshold: 10,     // 10%語音檢測閾值
  silenceTimeout: 5,        // 5秒靜音超時
  minSegmentTime: 1.0,      // 1秒最短分段時間
  segmentDelay: 1.0,        // 1秒分段延遲
  maxRecordingTime: 30      // 30秒最長連續錄音
})

// 語音相關狀態（由SmartVoiceRecorder管理）
// 移除舊的錄音相關變量

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
  
  // 檢查是否首次進入
  checkFirstTimeUser()
  
  // 每次都進行新的匿名登入，確保每個分頁有不同的用戶ID
  await performGuestLogin()
  
  // 載入用戶語言設定
  loadUserSettings()
  
  // 載入房間資料並連線
  await loadRoom()
  await connectWebSocket()
  
  // 如果是首次進入，自動顯示設定modal
  if (isFirstTime.value) {
    showSettingsModal.value = true
  }
})

onUnmounted(() => {
  disconnectWebSocket()
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

// 舊的錄音方法已移除，改用SmartVoiceRecorder組件

// 載入用戶設定
function loadUserSettings() {
  // 載入進階設定
  const savedAdvancedSettings = localStorage.getItem('userAdvancedSettings')
  if (savedAdvancedSettings) {
    const advanced = JSON.parse(savedAdvancedSettings)
    userSettings.value = { ...userSettings.value, ...advanced }
    inputLang.value = advanced.inputLang || 'zh-TW'
    outputLang.value = advanced.outputLang || 'zh-TW'
    console.log('📝 從 localStorage 載入進階設定:', advanced)
  }
  
  // 優先使用 sessionStore 中的用戶語言設定（確保用戶隔離）
  if (sessionStore.user?.inputLang) {
    inputLang.value = sessionStore.user.inputLang
    userSettings.value.inputLang = sessionStore.user.inputLang
    console.log(`📝 從 session 載入慣用語設定: ${inputLang.value}`)
  }
  if (sessionStore.user?.outputLang) {
    outputLang.value = sessionStore.user.outputLang
    userSettings.value.outputLang = sessionStore.user.outputLang
    console.log(`📝 從 session 載入主板語言設定: ${outputLang.value}`)
  }
  if (sessionStore.user?.displayName) {
    userSettings.value.displayName = sessionStore.user.displayName
  }
  
  // 如果 session 中沒有設定，才使用 localStorage 作為後備
  if (!sessionStore.user?.inputLang || !sessionStore.user?.outputLang) {
    const savedSettings = localStorage.getItem('userLanguageSettings')
    if (savedSettings) {
      const settings = JSON.parse(savedSettings)
      if (!sessionStore.user?.inputLang) {
        inputLang.value = settings.inputLang || 'zh-TW'
        userSettings.value.inputLang = settings.inputLang || 'zh-TW'
      }
      if (!sessionStore.user?.outputLang) {
        outputLang.value = settings.outputLang || 'zh-TW'
        userSettings.value.outputLang = settings.outputLang || 'zh-TW'
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

// 檢查是否首次進入
function checkFirstTimeUser() {
  const hasSettings = localStorage.getItem('userAdvancedSettings')
  isFirstTime.value = !hasSettings
}

// 開啟設定Modal
function openSettings() {
  showSettingsModal.value = true
}

// 關閉設定Modal
function closeSettingsModal() {
  showSettingsModal.value = false
}

// 保存用戶設定
async function saveUserSettings(settings: AdvancedSettings) {
  try {
    // 更新本地設定
    userSettings.value = { ...settings }
    
    // 更新語言設定
    inputLang.value = settings.inputLang
    outputLang.value = settings.outputLang
    
    // 保存到localStorage
    localStorage.setItem('userAdvancedSettings', JSON.stringify(settings))
    
    // 更新session store中的用戶資料
    if (sessionStore.user) {
      sessionStore.user.displayName = settings.displayName
      sessionStore.user.inputLang = settings.inputLang
      sessionStore.user.outputLang = settings.outputLang
      localStorage.setItem('user', JSON.stringify(sessionStore.user))
    }
    
    // 更新後端設定
    await updateSettings()
    
    // 如果是首次設定，標記為已完成
    if (isFirstTime.value) {
      isFirstTime.value = false
      closeSettingsModal()
    }
    
    console.log('✅ 用戶設定已保存:', settings)
  } catch (error) {
    console.error('❌ 保存設定失敗:', error)
    alert('保存設定失敗，請重試')
  }
}

// SmartVoiceRecorder 事件處理
function handleTranscript(result: { text: string; confidence: number; lang: string }) {
  console.log('✅ 收到語音識別結果:', result)
  
  // 透過 WebSocket 發送翻譯請求
  if (ws.value && ws.value.readyState === WebSocket.OPEN && sessionStore.user) {
    const message = {
      type: 'speech',
      room_id: roomId.value,
      speaker_id: sessionStore.user.id,
      speaker_name: userSettings.value.displayName || sessionStore.user.displayName,
      text: result.text,
      source_lang: result.lang,
      target_lang: outputLang.value,
      confidence: result.confidence
    }

    ws.value.send(JSON.stringify(message))
    console.log('📤 發送語音翻譯請求:', message)
  }
}

function handleVoiceError(error: string) {
  console.error('❌ 語音錄音錯誤:', error)
  // 可以在這裡添加用戶友好的錯誤提示
}

function handleRecordingStart() {
  console.log('🎤 開始智能錄音')
  isRecording.value = true
}

function handleRecordingEnd() {
  console.log('⏹️ 結束智能錄音')
  isRecording.value = false
}

// 語言代碼轉換為顯示名稱
function getLanguageName(langCode: string): string {
  const languageMap: Record<string, string> = {
    // 輸入語言 (語音識別)
    'zh-TW': '繁體中文',
    'zh-CN': '簡體中文', 
    'en-US': 'English',
    'ja-JP': '日本語',
    'ko-KR': '한국어',
    'es-ES': 'Español',
    'fr-FR': 'Français',
    'de-DE': 'Deutsch',
    'it-IT': 'Italiano',
    'pt-PT': 'Português',
    'ru-RU': 'Русский',
    'ar-SA': 'العربية',
    'hi-IN': 'हिन्दी',
    'th-TH': 'ไทย',
    'vi-VN': 'Tiếng Việt',
    'my-MM': 'မြန်မာ',
    'id-ID': 'Bahasa Indonesia',
    'ms-MY': 'Bahasa Melayu',
    
    // 輸出語言 (翻譯)
    'zh': '繁體中文',
    'en': 'English',
    'ja': '日本語',
    'ko': '한국어',
    'es': 'Español',
    'fr': 'Français',
    'de': 'Deutsch',
    'it': 'Italiano',
    'pt': 'Português',
    'ru': 'Русский',
    'ar': 'العربية',
    'hi': 'हिन्दी',
    'th': 'ไทย',
    'vi': 'Tiếng Việt',
    'my': 'မြန်မာ',
    'id': 'Bahasa Indonesia',
    'ms': 'Bahasa Melayu',
    'yue': '廣東話'
  }
  
  return languageMap[langCode] || langCode
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

.user-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  text-align: right;
}

.user-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
}

.lang-info {
  font-size: 0.8rem;
  color: #666;
  background: #f8f9fa;
  padding: 0.25rem 0.5rem;
  border-radius: 12px;
  border: 1px solid #e9ecef;
}

.settings-btn {
  background: #667eea;
  color: white;
  border: none;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  cursor: pointer;
  font-size: 1.2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.settings-btn:hover {
  background: #5a6fd8;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
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
  background: #ff4444 !important;
  color: white !important;
  transform: scale(1.1);
  box-shadow: 0 0 20px rgba(255, 68, 68, 0.7);
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