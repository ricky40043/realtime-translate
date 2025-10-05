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
          線上人數: {{ onlineCount }}
        </div>
      </div>
      <div class="room-actions">
        <button @click="$router.push('/settings')" class="btn-secondary">
          設定
        </button>
        <button @click="copyRoomLink" class="btn-secondary">
          分享房間
        </button>
        <button @click="copyUserLink" class="btn-primary">
          分享用戶連結
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
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { authApi, roomApi } from '../api/http'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()

// 響應式數據
const messagesContainer = ref<HTMLElement>()
const onlineCount = ref(0)
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

// 監聽訊息變化，自動滾動到底部
watch(() => sessionStore.boardMessages.length, async () => {
  await nextTick()
  scrollToBottom()
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
    // 自動檢測 WebSocket 地址：開發時使用 localhost，生產時使用當前主機
    const wsHost = process.env.NODE_ENV === 'production' ? window.location.hostname : 'localhost'
    const wsUrl = `ws://${wsHost}:8081/ws?roomId=${roomId.value}&userId=${sessionStore.user.id}&token=${sessionStore.token}`
    ws.value = new WebSocket(wsUrl)
    
    ws.value.onopen = () => {
      console.log('Host WebSocket connected')
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
  switch (message.type) {
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
      
    case 'room.userCount':
      onlineCount.value = message.count
      break
      
    case 'connection.established':
      console.log('Host connection established:', message)
      break
      
    default:
      console.log('Unknown message type:', message)
  }
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

// 複製用戶連結
function copyUserLink() {
  const url = `${window.location.origin}/user/${roomId.value}`
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
  font-size: 1.1rem;
  line-height: 1.4;
  color: #333;
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
</style>