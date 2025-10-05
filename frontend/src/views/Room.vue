<template>
  <div class="room-container">
    <!-- 頂部導航 -->
    <header class="room-header">
      <div class="room-info">
        <h1 v-if="sessionStore.currentRoom">{{ sessionStore.currentRoom.name }}</h1>
        <h1 v-else>載入中...</h1>
        <div class="connection-status">
          <span :class="['status-dot', { connected: sessionStore.isConnected }]"></span>
          {{ sessionStore.isConnected ? '已連線' : '連線中...' }}
        </div>
      </div>
      <div class="room-actions">
        <button @click="$router.push('/settings')" class="btn-secondary">
          設定
        </button>
        <button @click="copyRoomLink" class="btn-secondary">
          分享房間
        </button>
      </div>
    </header>

    <!-- 主要內容區域 -->
    <main class="room-main">
      <!-- 個人字幕區域 -->
      <section class="subtitle-section">
        <BigSubtitle 
          :subtitle="sessionStore.currentSubtitle"
          :user-lang="sessionStore.user?.preferredLang || 'zh-TW'"
        />
      </section>

      <!-- 主板訊息流 -->
      <section class="board-section">
        <h2>主板訊息</h2>
        <BoardFeed 
          :messages="sessionStore.boardMessages"
          :board-lang="sessionStore.currentRoom?.defaultBoardLang || 'en'"
        />
      </section>
    </main>

    <!-- 底部輸入區域 -->
    <footer class="room-footer">
      <div class="input-section">
        <div class="input-controls">
          <select v-model="inputLang" class="lang-select">
            <option value="">自動偵測</option>
            <option value="zh-TW">繁體中文</option>
            <option value="zh-CN">簡體中文</option>
            <option value="en">English</option>
            <option value="ja">日本語</option>
            <option value="ko">한국어</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
          </select>
          
          <!-- 語音模式選擇 -->
          <div class="voice-mode-selector">
            <label>
              <input type="radio" v-model="voiceMode" value="direct" />
              直接翻譯
            </label>
            <label>
              <input type="radio" v-model="voiceMode" value="staged" />
              分段處理
            </label>
          </div>
          
          <!-- 直接語音錄音組件 -->
          <VoiceRecorder 
            v-if="roomId && voiceMode === 'direct'"
            :room-id="roomId"
            @transcript="handleVoiceTranscript"
            @error="handleVoiceError"
          />
          
          <!-- 分段語音錄音組件 -->
          <VoiceRecorderStaged
            v-if="roomId && voiceMode === 'staged'"
            :room-id="roomId"
            @stt-preview="handleSTTPreview"
            @translation-start="handleTranslationStart"
            @error="handleVoiceError"
          />
        </div>
        <div class="input-area">
          <textarea
            v-model="inputText"
            @keydown="handleKeydown"
            placeholder="輸入訊息或使用麥克風..."
            class="message-input"
            rows="2"
          ></textarea>
          <button 
            @click="sendMessage"
            :disabled="!inputText.trim()"
            class="send-btn"
          >
            發送
          </button>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { authApi, roomApi, ingestApi } from '../api/http'
import BigSubtitle from '../components/BigSubtitle.vue'
import BoardFeed from '../components/BoardFeed.vue'
import VoiceRecorder from '../components/VoiceRecorder.vue'
import VoiceRecorderStaged from '../components/VoiceRecorderStaged.vue'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()

// 響應式數據
const inputText = ref('')
const inputLang = ref('')
const voiceMode = ref('staged') // 'direct' 或 'staged'
const ws = ref<WebSocket | null>(null)

// 房間 ID
const roomId = ref<string>('')

// 初始化
onMounted(async () => {
  // 載入認證資料
  sessionStore.loadAuth()
  
  // 處理房間 ID
  const routeRoomId = route.params.roomId as string
  if (routeRoomId) {
    roomId.value = routeRoomId
  } else {
    // 沒有房間 ID，建立新房間
    await createNewRoom()
  }
  
  // 如果未登入，先進行匿名登入
  if (!sessionStore.isAuthenticated) {
    await performGuestLogin()
  }
  
  // 載入房間資料並連線
  await loadRoom()
  await connectWebSocket()
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
    const guestName = `訪客_${Math.random().toString(36).substr(2, 6)}`
    const response = await authApi.guestLogin(guestName, 'zh-TW')
    
    sessionStore.setAuth(
      {
        id: response.user_id,
        displayName: response.display_name,
        preferredLang: response.preferred_lang
      },
      response.token
    )
  } catch (error) {
    console.error('Guest login failed:', error)
    alert('登入失敗，請重新整理頁面')
  }
}

// 建立新房間
async function createNewRoom() {
  try {
    const roomName = `房間_${new Date().toLocaleString()}`
    const response = await roomApi.createRoom(roomName, 'en')
    roomId.value = response.id
    
    // 更新 URL
    router.replace(`/room/${roomId.value}`)
  } catch (error) {
    console.error('Create room failed:', error)
    alert('建立房間失敗')
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
    // 使用當前主機名和端口
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = window.location.host
    const wsUrl = `${wsProtocol}//${wsHost}/ws?roomId=${roomId.value}&userId=${sessionStore.user.id}&token=${sessionStore.token}`
    ws.value = new WebSocket(wsUrl)
    
    ws.value.onopen = () => {
      console.log('WebSocket connected')
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
      console.log('WebSocket disconnected')
      sessionStore.setWebSocket(null)
      
      // 自動重連
      setTimeout(() => {
        if (roomId.value && sessionStore.user) {
          connectWebSocket()
        }
      }, 3000)
    }
    
    ws.value.onerror = (error) => {
      console.error('WebSocket error:', error)
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
  switch (message.type) {
    case 'personal.subtitle':
      sessionStore.addPersonalSubtitle({
        id: message.messageId,
        speakerId: message.speakerId || '',
        speakerName: message.speakerName || '',
        text: message.text,
        sourceLang: '',
        targetLang: message.targetLang,
        timestamp: message.timestamp,
        type: 'personal'
      })
      break
      
    case 'board.post':
      sessionStore.addBoardMessage({
        id: message.messageId,
        speakerId: message.speakerId,
        speakerName: message.speakerName,
        text: message.text,
        sourceLang: message.sourceLang,
        targetLang: message.targetLang,
        timestamp: message.timestamp,
        type: 'board'
      })
      break
      
    case 'connection.established':
      console.log('Connection established:', message)
      break
      
    default:
      console.log('Unknown message type:', message)
  }
}

// 發送訊息
async function sendMessage() {
  if (!inputText.value.trim() || !roomId.value) return
  
  try {
    await ingestApi.sendText(
      roomId.value,
      inputText.value.trim(),
      inputLang.value || undefined,
      true
    )
    
    inputText.value = ''
  } catch (error) {
    console.error('Send message failed:', error)
    alert('發送訊息失敗')
  }
}

// 處理鍵盤事件
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

// 處理語音轉錄結果
function handleVoiceTranscript(result: { text: string; confidence: number; lang: string }) {
  console.log('🎤 語音轉錄結果:', result)
  
  // 將轉錄文字填入輸入框
  inputText.value = result.text
  
  // 如果信心度夠高，自動發送
  if (result.confidence > 0.8) {
    setTimeout(() => {
      sendMessage()
    }, 500) // 短暫延遲讓用戶看到文字
  } else {
    // 信心度較低時提示用戶確認
    console.log(`⚠️ 語音識別信心度較低 (${result.confidence})，請確認文字內容`)
  }
}

// 處理語音錯誤
function handleVoiceError(error: string) {
  console.error('🎤 語音輸入錯誤:', error)
  alert(`語音輸入錯誤: ${error}`)
}

// 處理 STT 預覽（分段語音第一步）
function handleSTTPreview(result: { transcript: string; confidence: number; detectedLang: string }) {
  console.log('🎤 STT 預覽結果:', result)
  
  // 可以在這裡顯示 STT 預覽通知
  if (result.confidence < 0.7) {
    console.warn(`⚠️ 語音識別信心度較低 (${Math.round(result.confidence * 100)}%)，請確認文字內容`)
  }
}

// 處理翻譯開始（分段語音第二步）
function handleTranslationStart(data: { messageId: string; finalText: string; sourceLang: string }) {
  console.log('🔄 翻譯處理開始:', data)
  
  // 顯示處理中的狀態
  console.log(`正在翻譯: "${data.finalText}" (${data.sourceLang})`)
}

// 複製房間連結
function copyRoomLink() {
  const url = `${window.location.origin}/room/${roomId.value}`
  navigator.clipboard.writeText(url).then(() => {
    alert('房間連結已複製到剪貼簿')
  }).catch(() => {
    alert(`房間連結：${url}`)
  })
}
</script>

<style scoped>
.room-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.room-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
}

.room-info h1 {
  margin: 0;
  font-size: 1.5rem;
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

.room-actions {
  display: flex;
  gap: 1rem;
}

.room-main {
  flex: 1;
  display: grid;
  grid-template-rows: 1fr 300px;
  gap: 2rem;
  padding: 2rem;
  overflow: hidden;
}

.subtitle-section {
  display: flex;
  align-items: center;
  justify-content: center;
}

.board-section {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 1rem;
  padding: 1.5rem;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.board-section h2 {
  margin: 0 0 1rem 0;
  font-size: 1.2rem;
  color: #333;
}

.room-footer {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  padding: 1.5rem 2rem;
  border-top: 1px solid rgba(0, 0, 0, 0.1);
}

.input-section {
  max-width: 800px;
  margin: 0 auto;
}

.input-controls {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  align-items: center;
}

.lang-select {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 0.5rem;
  background: white;
}

.voice-mode-selector {
  display: flex;
  gap: 1rem;
  align-items: center;
  background: #f8f9fa;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid #dee2e6;
}

.voice-mode-selector label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  color: #495057;
}

.voice-mode-selector input[type="radio"] {
  margin: 0;
}


.input-area {
  display: flex;
  gap: 1rem;
  align-items: flex-end;
}

.message-input {
  flex: 1;
  padding: 0.75rem;
  border: 1px solid #ddd;
  border-radius: 0.5rem;
  resize: vertical;
  font-family: inherit;
  font-size: 1rem;
}

.message-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.send-btn {
  padding: 0.75rem 1.5rem;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.send-btn:hover:not(:disabled) {
  background: #5a6fd8;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 0.5rem 1rem;
  background: white;
  color: #667eea;
  border: 1px solid #667eea;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s;
}

.btn-secondary:hover {
  background: #667eea;
  color: white;
}
</style>