<template>
  <div class="room-container">
    <!-- 頂部導航 -->
    <header class="room-header">
      <div class="room-info">
        <h1>🌍 多語言即時翻譯測試</h1>
        <div class="subtitle">
          使用語音或文字進行多語言翻譯測試
        </div>
      </div>
      <div class="room-actions">
        <button @click="createRoom" class="btn-primary">
          🚀 創建房間
        </button>
      </div>
    </header>

    <!-- 主要內容區域 -->
    <main class="room-main">
      <!-- 翻譯測試區域 -->
      <section class="translation-test-section">
        <div class="test-container">
          <h2>🎤 語音翻譯測試</h2>
          <div class="test-description">
            選擇源語言和目標語言，使用語音或文字進行翻譯測試
          </div>
          
          <!-- 語言選擇 -->
          <div class="language-selector">
            <div class="lang-group">
              <label>源語言:</label>
              <select v-model="sourceLang" class="lang-select">
                <option value="">自動偵測</option>
                <option value="zh-TW">繁體中文</option>
                <option value="zh-CN">簡體中文</option>
                <option value="en">English</option>
                <option value="ja">日本語</option>
                <option value="ko">한국어</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
                <option value="my">မြန်မာ (緬甸文)</option>
                <option value="id">Bahasa Indonesia (印尼文)</option>
                <option value="ms">Bahasa Melayu (馬來文)</option>
                <option value="yue">廣東話</option>
              </select>
            </div>
            <div class="arrow">→</div>
            <div class="lang-group">
              <label>目標語言:</label>
              <select v-model="targetLang" class="lang-select">
                <option value="zh-TW">繁體中文</option>
                <option value="zh-CN">簡體中文</option>
                <option value="en">English</option>
                <option value="ja">日本語</option>
                <option value="ko">한국어</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
                <option value="my">မြန်မာ (緬甸文)</option>
                <option value="id">Bahasa Indonesia (印尼文)</option>
                <option value="ms">Bahasa Melayu (馬來文)</option>
                <option value="yue">廣東話</option>
              </select>
            </div>
          </div>
          
          <!-- 翻譯結果顯示 -->
          <div class="translation-result" v-if="translationResult">
            <div class="source-text">
              <strong>原文 ({{ getLanguageName(translationResult.sourceLang) }}):</strong>
              <p>{{ translationResult.sourceText }}</p>
            </div>
            <div class="target-text">
              <strong>翻譯 ({{ getLanguageName(translationResult.targetLang) }}):</strong>
              <p>{{ translationResult.translatedText }}</p>
            </div>
          </div>
        </div>
      </section>
    </main>

    <!-- 底部輸入區域 -->
    <footer class="room-footer">
      <div class="input-section">
        <div class="input-controls">
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
          
          <!-- 語音錄音組件 (測試模式) -->
          <div class="voice-recorder-container">
            <button 
              @mousedown="startRecording" 
              @mouseup="stopRecording"
              @touchstart="startRecording"
              @touchend="stopRecording"
              :disabled="isRecording"
              class="voice-test-btn"
            >
              <span class="voice-icon">{{ isRecording ? '🔴' : '🎤' }}</span>
              <span class="voice-text">{{ isRecording ? '錄音中...' : '按住說話' }}</span>
            </button>
          </div>
        </div>
        
        <div class="input-area">
          <textarea
            v-model="inputText"
            @keydown="handleKeydown"
            placeholder="輸入文字進行翻譯測試..."
            class="message-input"
            rows="2"
          ></textarea>
          <button 
            @click="translateText"
            :disabled="!inputText.trim()"
            class="translate-btn"
          >
            翻譯
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
const sourceLang = ref('')
const targetLang = ref('zh-TW')
const voiceMode = ref('direct')
const isRecording = ref(false)
const translationResult = ref<{
  sourceText: string
  translatedText: string
  sourceLang: string
  targetLang: string
} | null>(null)

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
    // 沒有房間 ID，停留在首頁，不自動創建房間
    console.log('📍 停留在房間首頁，等待用戶手動創建房間')
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
  // 翻譯測試頁面無需清理
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
    console.log(`👤 進行匿名登入: ${guestName}`)
    
    const response = await authApi.guestLogin(guestName, 'zh-TW', 'zh-TW', 'en')
    
    const userInfo = {
      id: response.user_id,
      displayName: response.display_name,
      preferredLang: response.preferred_lang,
      inputLang: response.input_lang,
      outputLang: response.output_lang
    }
    
    sessionStore.setAuth(userInfo, response.token)
    console.log(`✅ 匿名登入成功: ${userInfo.displayName}`)
  } catch (error) {
    console.error('❌ 匿名登入失敗:', error)
    alert('登入失敗，請重新整理頁面')
  }
}

// 建立新房間功能已整合到 createRoom() 函數中

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
  
  // WebSocket 功能已移除
  
  try {
    // 使用當前頁面的協議和主機
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = window.location.host
    const wsUrl = `${wsProtocol}//${wsHost}/ws?roomId=${roomId.value}&userId=${sessionStore.user.id}&token=${sessionStore.token}`
    // WebSocket 功能已移除，翻譯測試頁面不需要
  } catch (error) {
    console.error('Connect WebSocket failed:', error)
  }
}

// WebSocket 功能已移除

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



// 處理語音轉錄結果 (測試模式用)
function handleVoiceTranscript(result: { text: string; confidence: number; lang: string }) {
  console.log('🎤 語音轉錄結果:', result)
  
  // 將轉錄文字填入輸入框
  inputText.value = result.text
  
  // 自動觸發翻譯
  setTimeout(() => {
    translateText()
  }, 500)
}

// 創建房間
async function createRoom() {
  try {
    // 先檢查是否已登入，如果沒有先進行匿名登入
    if (!sessionStore.isAuthenticated) {
      console.log('👤 創建房間前先進行匿名登入')
      await performGuestLogin()
    }
    
    const roomName = `測試房間_${new Date().toLocaleString()}`
    console.log('🏠 創建新房間:', roomName)
    
    // 調用後端 API 創建房間
    const response = await roomApi.createRoom(roomName, 'en')
    console.log('✅ 房間創建成功:', response)
    
    // 跳轉到 host 頁面
    router.push(`/host/${response.id}`)
  } catch (error) {
    console.error('❌ 創建房間失敗:', error)
    alert('創建房間失敗，請重試')
  }
}

// 重複的匿名登入函數已刪除，使用上方現有的 performGuestLogin

// 翻譯文字
async function translateText() {
  if (!inputText.value.trim()) return
  
  try {
    // 模擬翻譯 API 調用
    console.log('翻譯文字:', {
      text: inputText.value,
      from: sourceLang.value || 'auto',
      to: targetLang.value
    })
    
    // 這裡應該調用實際的翻譯 API
    // 暫時使用模擬數據
    translationResult.value = {
      sourceText: inputText.value,
      translatedText: `[翻譯結果] ${inputText.value}`,
      sourceLang: sourceLang.value || 'auto',
      targetLang: targetLang.value
    }
    
    // 清空輸入框
    inputText.value = ''
  } catch (error) {
    console.error('翻譯失敗:', error)
    alert('翻譯失敗，請重試')
  }
}

// 開始錄音
function startRecording() {
  isRecording.value = true
  console.log('開始錄音...')
  // 這裡會實現語音識別功能
}

// 停止錄音
function stopRecording() {
  isRecording.value = false
  console.log('停止錄音')
  // 這裡會處理錄音結果
}

// 獲取語言名稱
function getLanguageName(langCode: string): string {
  const langMap: Record<string, string> = {
    'zh-TW': '繁體中文',
    'zh-CN': '簡體中文',
    'en': 'English',
    'ja': '日本語',
    'ko': '한국어',
    'es': 'Español',
    'fr': 'Français',
    'de': 'Deutsch',
    'my': 'မြန်မာ (緬甸文)',
    'id': 'Bahasa Indonesia (印尼文)',
    'ms': 'Bahasa Melayu (馬來文)',
    'yue': '廣東話',
    'auto': '自動偵測'
  }
  return langMap[langCode] || langCode
}

// 處理鍵盤事件
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    translateText()
  }
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
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.translation-test-section {
  width: 100%;
  max-width: 800px;
}

.test-container {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  padding: 2rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.test-container h2 {
  margin: 0 0 1rem 0;
  color: #333;
  font-size: 1.8rem;
}

.test-description {
  color: #666;
  margin-bottom: 2rem;
  font-size: 1rem;
}

.language-selector {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.lang-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 200px;
}

.lang-group label {
  font-weight: 600;
  color: #333;
  font-size: 0.9rem;
}

.arrow {
  font-size: 1.5rem;
  color: #667eea;
  font-weight: bold;
}

.translation-result {
  background: #f8f9fa;
  border-radius: 12px;
  padding: 1.5rem;
  margin-top: 2rem;
  text-align: left;
}

.source-text, .target-text {
  margin-bottom: 1rem;
}

.source-text p, .target-text p {
  margin: 0.5rem 0 0 0;
  padding: 1rem;
  background: white;
  border-radius: 8px;
  border-left: 4px solid #667eea;
}

.target-text p {
  border-left-color: #28a745;
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

.translate-btn {
  padding: 0.75rem 1.5rem;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.translate-btn:hover:not(:disabled) {
  background: #218838;
}

.translate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  padding: 0.75rem 1.5rem;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
  font-size: 1rem;
}

.btn-primary:hover {
  background: #0056b3;
}

.voice-test-btn {
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

.voice-test-btn:hover:not(:disabled) {
  background: #218838;
  transform: scale(1.05);
}

.voice-test-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
  transform: none;
}

.voice-test-btn.recording {
  background: #dc3545;
  animation: pulse 1s infinite;
}

.voice-icon {
  font-size: 1.5rem;
}

.voice-text {
  font-size: 0.9rem;
  font-weight: 500;
}

.subtitle {
  color: #666;
  font-size: 1rem;
  margin-top: 0.5rem;
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

/* Mobile responsive styles */
@media (max-width: 768px) {
  .room-header {
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
    justify-content: center;
    gap: 0.5rem;
  }
  
  .btn-secondary {
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
  }
  
  .room-main {
    grid-template-rows: 1fr 250px;
    padding: 1rem;
    gap: 1rem;
  }
  
  .board-section {
    padding: 1rem;
    border-radius: 0.75rem;
  }
  
  .board-section h2 {
    font-size: 1rem;
  }
  
  .room-footer {
    padding: 1rem;
  }
  
  .input-controls {
    flex-direction: column;
    gap: 0.75rem;
    align-items: stretch;
  }
  
  .lang-select {
    width: 100%;
    padding: 0.75rem;
    font-size: 1rem;
  }
  
  .voice-mode-selector {
    justify-content: center;
    padding: 0.75rem;
  }
  
  .voice-mode-selector label {
    font-size: 1rem;
  }
  
  .input-area {
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .message-input {
    min-height: 80px;
    padding: 1rem;
    font-size: 1rem;
  }
  
  .send-btn {
    width: 100%;
    padding: 1rem;
    font-size: 1.1rem;
  }
}

@media (max-width: 480px) {
  .room-header {
    padding: 0.75rem;
  }
  
  .room-info h1 {
    font-size: 1rem;
  }
  
  .connection-status {
    font-size: 0.8rem;
  }
  
  .btn-secondary {
    padding: 0.4rem 0.6rem;
    font-size: 0.75rem;
  }
  
  .room-main {
    grid-template-rows: 1fr 200px;
    padding: 0.75rem;
    gap: 0.75rem;
  }
  
  .board-section {
    padding: 0.75rem;
  }
  
  .board-section h2 {
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
  }
  
  .room-footer {
    padding: 0.75rem;
  }
  
  .input-controls {
    gap: 0.5rem;
  }
  
  .lang-select {
    padding: 0.6rem;
    font-size: 0.9rem;
  }
  
  .voice-mode-selector {
    padding: 0.6rem;
    gap: 0.75rem;
  }
  
  .voice-mode-selector label {
    font-size: 0.85rem;
  }
  
  .input-area {
    gap: 0.5rem;
  }
  
  .message-input {
    min-height: 70px;
    padding: 0.75rem;
    font-size: 0.9rem;
  }
  
  .send-btn {
    padding: 0.75rem;
    font-size: 1rem;
  }
}
</style>