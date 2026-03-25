<template>
  <div class="host-board-container">
    <!-- 頂部導航 -->
    <header class="host-header">
      <div class="room-info">
        <h1 v-if="sessionStore.currentRoom">{{ sessionStore.currentRoom.name }} - 主板</h1>
        <h1 v-else>載入中...</h1>
        <div class="connection-status">
          <span :class="['status-dot', { connected: sessionStore.isConnected }]"></span>
          {{ sessionStore.isConnected ? '已連線' : '連線中...' }}
        </div>
        <div class="room-stats">
          線上人數: {{ onlineCount }} | 主板訊息: {{ sessionStore.boardMessages.length }}
        </div>
      </div>
      <div class="room-actions">
        <button @click="showShareModal = true" class="btn-primary">
          📱 分享房間
        </button>
        <button @click="copyUserLink" class="btn-secondary">
          複製連結
        </button>
        <button @click="$router.push('/settings')" class="btn-secondary">
          設定
        </button>
        <button @click="showDebug = !showDebug" class="btn-secondary">
          {{ showDebug ? '隱藏除錯' : '顯示除錯' }}
        </button>
      </div>
    </header>

    <!-- 主板訊息滿版顯示 -->
    <main class="host-main">
      <div class="board-messages-container">
        <div class="board-messages" ref="messagesContainer">
          <div 
            v-for="message in sessionStore.boardMessages" 
            :key="message.id"
            class="message-item"
            :class="{ 'own-message': message.speakerId === sessionStore.user?.id }"
          >
            <div class="message-header">
              <span class="speaker-name">{{ message.speakerName }}</span>
              <span class="message-time">{{ formatTime(message.timestamp) }}</span>
              <span class="language-badge">{{ message.sourceLang }} → {{ message.targetLang }}</span>
            </div>
            <div class="message-content">{{ message.text }}</div>
          </div>
        </div>
      </div>

      <!-- Debug 面板 -->
      <div v-if="showDebug" class="debug-panel">
        <h3>WebSocket 除錯訊息 ({{ debugMessages.length }})</h3>
        <div class="debug-list">
          <div v-for="(m, idx) in debugMessages" :key="idx" class="debug-item">
            <div class="debug-meta">{{ m.ts }} - {{ m.type }}</div>
            <pre class="debug-json">{{ m.pretty }}</pre>
          </div>
        </div>
      </div>
    </main>

    <!-- 分享房間模態窗 -->
    <div v-if="showShareModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h2>📱 分享房間</h2>
          <button @click="closeModal" class="close-btn">✕</button>
        </div>
        
        <div class="modal-body">
          <!-- QR Code 區域 -->
          <div class="qr-section">
            <h3>掃描 QR Code 加入房間</h3>
            <div class="qr-container">
              <canvas ref="qrCanvas" class="qr-code"></canvas>
            </div>
          </div>
          
          <!-- 短網址區域 -->
          <div class="url-section">
            <h3>或使用連結加入</h3>
            <div class="url-container">
              <input 
                ref="urlInput"
                :value="userUrl" 
                readonly 
                class="url-input"
              />
              <button @click="copyUrl" class="copy-btn">
                {{ urlCopied ? '✅ 已複製' : '📋 複製' }}
              </button>
            </div>
          </div>
          
          <!-- 使用說明 -->
          <div class="instructions">
            <p>👥 邀請其他人：</p>
            <ul>
              <li>📱 手機用戶可掃描 QR Code</li>
              <li>💻 電腦用戶可複製連結</li>
              <li>🎤 加入後即可開始語音翻譯</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { authApi, roomApi } from '../api/http'
import QRCode from 'qrcode'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()

// 響應式數據
const messagesContainer = ref<HTMLElement>()
const onlineCount = ref(0)
const ws = ref<WebSocket | null>(null)
const showDebug = ref(true)
type DebugEntry = { ts: string; type: string; raw: string; pretty: string }
const debugMessages = ref<DebugEntry[]>([])

// 房間 ID
const roomId = ref<string>('')

// 分享功能相關
const showShareModal = ref(false)
const qrCanvas = ref<HTMLCanvasElement>()
const urlInput = ref<HTMLInputElement>()
const urlCopied = ref(false)
const userUrl = ref('')

// 初始化
onMounted(async () => {
  // 載入認證資料
  sessionStore.loadAuth()
  
  // 處理房間 ID
  const routeRoomId = route.params.roomId as string
  if (routeRoomId) {
    roomId.value = routeRoomId
    userUrl.value = `${window.location.origin}/user?roomId=${routeRoomId}`
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

// 監聽訊息變化，自動滾動到底部
watch(() => sessionStore.boardMessages.length, async () => {
  await nextTick()
  scrollToBottom()
})

// 監聽分享模態窗顯示，生成 QR Code
watch(showShareModal, async (isShown) => {
  if (isShown) {
    await nextTick()
    generateQRCode()
  }
})

// 匿名登入
async function performGuestLogin() {
  try {
    const hostName = `主板_${Math.random().toString(36).substr(2, 6)}`
    const response = await authApi.guestLogin(hostName, 'zh-TW', '', 'zh-TW')
    
    sessionStore.setAuth(
      {
        id: response.user_id,
        displayName: response.display_name,
        preferredLang: response.preferred_lang,
        inputLang: response.input_lang,
        outputLang: response.output_lang
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
    const roomName = `主板房間_${new Date().toLocaleString()}`
    const response = await roomApi.createRoom(roomName, 'zh-TW')
    roomId.value = response.id
    
    // 更新 URL
    router.replace(`/host/${roomId.value}`)
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
    // 自動檢測 WebSocket 地址：使用當前頁面的協議和主機
    const baseWsUrl = import.meta.env.VITE_WS_URL || (() => { const p = window.location.protocol === 'https:' ? 'wss:' : 'ws:'; return `${p}//${window.location.host}/ws`; })();
    const wsUrl = `${baseWsUrl}?roomId=${roomId.value}&userId=${sessionStore.user.id}&token=${sessionStore.token}`
    ws.value = new WebSocket(wsUrl)
    
    ws.value.onopen = () => {
      console.log('Host WebSocket connected')
      sessionStore.setWebSocket(ws.value)
    }
    
    ws.value.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        // 緩存除錯資料
        debugMessages.value.push({
          ts: new Date().toISOString(),
          type: message?.type || 'unknown',
          raw: event.data,
          pretty: JSON.stringify(message, null, 2)
        })
        if (debugMessages.value.length > 200) {
          debugMessages.value.splice(0, debugMessages.value.length - 200)
        }
        console.log('🔄 Host收到WebSocket訊息:', message)
        console.log('🔍 訊息類型:', message.type)
        console.log('🔍 訊息內容:', JSON.stringify(message, null, 2))
        handleWebSocketMessage(message)
      } catch (error) {
        console.error('❌ Parse WebSocket message failed:', error)
        console.error('❌ 原始資料:', event.data)
        // 無法解析也記錄
        debugMessages.value.push({
          ts: new Date().toISOString(),
          type: 'parse_error',
          raw: String(event.data),
          pretty: String(event.data)
        })
      }
    }
    
    ws.value.onclose = () => {
      console.log('Host WebSocket disconnected')
      sessionStore.setWebSocket(null)
      
      // 自動重連
      setTimeout(() => {
        if (roomId.value && sessionStore.user) {
          connectWebSocket()
        }
      }, 3000)
    }
    
    ws.value.onerror = (error) => {
      console.error('Host WebSocket error:', error)
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
  console.log(`🎯 Host處理訊息: ${message.type}`)
  
  switch (message.type) {
    case 'board.post':
      console.log('📢 【HOST收到主板訊息】:', message.text, `[${message.sourceLang}→${message.targetLang}]`, `(${message.speakerName})`)
      console.log('📢 完整訊息內容:', message)
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
      console.log('📢 已添加到 boardMessages，當前數量:', sessionStore.boardMessages.length)
      break
      
    case 'personal.subtitle':
      console.log('👤 【HOST收到個人字幕】(應該忽略):', message.text, `(${message.speakerName})`)
      // Host不處理個人字幕，但記錄收到
      break
      
    case 'user.connected':
      console.log('👋 【用戶連線】:', message.message, `(房間人數: ${message.userCount})`)
      onlineCount.value = message.userCount
      break
      
    case 'user.disconnected':
      console.log('👋 【用戶離開】:', message.message, `(房間人數: ${message.userCount})`)
      onlineCount.value = message.userCount
      break
      
    case 'connection.established':
      console.log('🎉 【Host連線已建立】:', message)
      break
      
    case 'room.userCount':
      console.log('📊 【房間人數更新】:', message.count)
      onlineCount.value = message.count
      break
      
    default:
      console.log('❓ 【未知訊息類型】:', message.type, message)
  }
  
  console.log(`✅ Host處理完成: ${message.type}`)
}

// 複製房間連結
function copyRoomLink() {
  const url = `${window.location.origin}/host/${roomId.value}`
  navigator.clipboard.writeText(url).then(() => {
    alert('主板房間連結已複製到剪貼簿')
  }).catch(() => {
    alert(`主板房間連結：${url}`)
  })
}

// 分享功能
async function generateQRCode() {
  if (!qrCanvas.value) return
  
  try {
    const url = `${window.location.origin}/user?roomId=${roomId.value}`
    await QRCode.toCanvas(qrCanvas.value, url, {
      width: 200,
      margin: 2,
      color: {
        dark: '#000000',
        light: '#FFFFFF'
      }
    })
    console.log('QR Code generated for:', url)
  } catch (error) {
    console.error('生成 QR Code 失敗:', error)
  }
}

// 關閉模態窗
function closeModal() {
  showShareModal.value = false
  urlCopied.value = false
}

// 複製網址
async function copyUrl() {
  try {
    await navigator.clipboard.writeText(userUrl.value)
    urlCopied.value = true
    setTimeout(() => {
      urlCopied.value = false
    }, 2000)
  } catch (error) {
    // 備用方案
    if (urlInput.value) {
      urlInput.value.select()
      document.execCommand('copy')
      urlCopied.value = true
      setTimeout(() => {
        urlCopied.value = false
      }, 2000)
    }
  }
}

// 複製用戶連結
function copyUserLink() {
  const url = `${window.location.origin}/user?roomId=${roomId.value}`
  navigator.clipboard.writeText(url).then(() => {
    alert('用戶參與連結已複製到剪貼簿')
  }).catch(() => {
    alert(`用戶參與連結：${url}`)
  })
}

// 格式化時間
function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString()
}

// 滾動到底部
function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}
</script>

<style scoped>
.host-board-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
}

.host-header {
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

.room-stats {
  font-size: 0.8rem;
  color: #888;
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

.btn-secondary, .btn-primary {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.3s;
}

.btn-secondary {
  background: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background: #5a6268;
}

.btn-primary {
  background: #007bff;
  color: white;
}

.btn-primary:hover {
  background: #0056b3;
}

.host-main {
  flex: 1;
  padding: 2rem;
  overflow: hidden;
}

.board-messages-container {
  height: 100%;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.board-messages {
  height: 100%;
  overflow-y: auto;
  padding-right: 1rem;
}

.message-item {
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: #f8f9fa;
  border-radius: 8px;
  border-left: 4px solid #007bff;
  transition: all 0.3s;
}

.message-item:hover {
  background: #e9ecef;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.message-item.own-message {
  border-left-color: #28a745;
  background: #d4edda;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
  color: #666;
}

.speaker-name {
  font-weight: 600;
  color: #333;
}

.language-badge {
  background: #007bff;
  color: white;
  padding: 0.2rem 0.5rem;
  border-radius: 12px;
  font-size: 0.75rem;
}

.message-content {
  font-size: 1.4rem;
  line-height: 1.5;
  color: #333;
  font-weight: 500;
}

/* 滾動條樣式 */
.board-messages::-webkit-scrollbar {
  width: 6px;
}

.board-messages::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.board-messages::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.board-messages::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* Debug 面板樣式 */
.debug-panel {
  margin-top: 1rem;
  background: rgba(0, 0, 0, 0.75);
  color: #e9ecef;
  padding: 1rem;
  border-radius: 8px;
  max-height: 260px;
  overflow: auto;
}
.debug-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.debug-item {
  background: rgba(255, 255, 255, 0.07);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
}
.debug-meta {
  font-size: 0.8rem;
  color: #b8bcc2;
  margin-bottom: 0.25rem;
}
.debug-json {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.85rem;
}

/* Mobile responsive styles */
@media (max-width: 768px) {
  .host-header {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
  }
  
  .room-info {
    text-align: center;
    width: 100%;
  }
  
  .room-info h1 {
    font-size: 1.2rem;
  }
  
  .room-actions {
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.5rem;
  }
  
  .btn-secondary, .btn-primary {
    padding: 0.75rem 1rem;
    font-size: 0.8rem;
    min-width: 80px;
  }
  
  .host-main {
    padding: 1rem;
  }
  
  .board-messages-container {
    padding: 1rem;
    border-radius: 8px;
  }
  
  .board-messages {
    padding-right: 0.5rem;
  }
  
  .message-item {
    margin-bottom: 1rem;
    padding: 0.75rem;
  }
  
  .message-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.25rem;
  }
  
  .message-content {
    font-size: 1rem;
  }
  
  .debug-panel {
    max-height: 200px;
    padding: 0.75rem;
  }
}

@media (max-width: 480px) {
  .host-header {
    padding: 0.75rem;
  }
  
  .room-info h1 {
    font-size: 1rem;
  }
  
  .connection-status {
    font-size: 0.8rem;
  }
  
  .room-stats {
    font-size: 0.7rem;
  }
  
  .room-actions {
    gap: 0.25rem;
  }
  
  .btn-secondary, .btn-primary {
    padding: 0.5rem 0.75rem;
    font-size: 0.75rem;
    min-width: 70px;
  }
  
  .host-main {
    padding: 0.75rem;
  }
  
  .board-messages-container {
    padding: 0.75rem;
  }
  
  .message-item {
    padding: 0.5rem;
    margin-bottom: 0.75rem;
  }
  
  .message-header {
    font-size: 0.75rem;
  }
  
  .language-badge {
    font-size: 0.7rem;
    padding: 0.15rem 0.4rem;
  }
  
  .message-content {
    font-size: 1.2rem;
  }
  
  .debug-panel {
    max-height: 150px;
    padding: 0.5rem;
  }
  
  .debug-json {
    font-size: 0.75rem;
  }
}

/* 分享模態窗樣式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 16px;
  padding: 0;
  max-width: 500px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid #eee;
}

.modal-header h2 {
  margin: 0;
  color: #333;
  font-size: 1.5rem;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #666;
  padding: 0.5rem;
  border-radius: 50%;
  transition: all 0.3s;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #333;
}

.modal-body {
  padding: 1.5rem;
}

.qr-section, .url-section {
  margin-bottom: 2rem;
}

.qr-section h3, .url-section h3 {
  margin: 0 0 1rem 0;
  color: #333;
  font-size: 1.1rem;
}

.qr-container {
  text-align: center;
  padding: 1rem;
  background: #f9f9f9;
  border-radius: 12px;
  border: 2px dashed #ddd;
}

.qr-code {
  max-width: 100%;
  height: auto;
}

.url-container {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.url-input {
  flex: 1;
  padding: 0.75rem;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 0.9rem;
  background: #f9f9f9;
  color: #333;
  font-family: monospace;
}

.copy-btn {
  padding: 0.75rem 1rem;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  transition: all 0.3s;
  white-space: nowrap;
}

.copy-btn:hover {
  background: #0056b3;
}

.instructions {
  background: #f0f7ff;
  padding: 1rem;
  border-radius: 8px;
  border-left: 4px solid #007bff;
}

.instructions p {
  margin: 0 0 0.5rem 0;
  font-weight: 600;
  color: #333;
}

.instructions ul {
  margin: 0;
  padding-left: 1.2rem;
}

.instructions li {
  margin: 0.25rem 0;
  color: #666;
}

/* 手機版分享模態窗 */
@media (max-width: 768px) {
  .modal-content {
    width: 95%;
    max-height: 90vh;
  }
  
  .modal-header {
    padding: 1rem;
  }
  
  .modal-header h2 {
    font-size: 1.2rem;
  }
  
  .modal-body {
    padding: 1rem;
  }
  
  .url-container {
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .url-input {
    width: 100%;
    font-size: 0.8rem;
  }
  
  .copy-btn {
    width: 100%;
    padding: 1rem;
  }
  
  .qr-container {
    padding: 0.5rem;
  }
}
</style>