<template>
  <div class="settings-container">
    <header class="settings-header">
      <button @click="$router.back()" class="back-btn">
        ← 返回房間
      </button>
      <h1>設定</h1>
    </header>

    <main class="settings-main">
      <div class="settings-content">
        
        <!-- 個人設定 -->
        <section class="settings-section">
          <h2>🧑‍💼 個人設定</h2>
          <div class="setting-item">
            <label class="setting-label">
              顯示名稱
            </label>
            <input 
              v-model="localUserName"
              type="text" 
              class="setting-input"
              placeholder="輸入您的名稱"
            />
          </div>
          
          <div class="setting-item">
            <label class="setting-label">
              偏好語言（個人字幕語言）
            </label>
            <select v-model="localUserLang" class="setting-select">
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
            </select>
            <p class="setting-description">
              選擇您希望看到的字幕語言
            </p>
          </div>
          
          <button @click="savePersonalSettings" :disabled="saving" class="save-btn">
            {{ saving ? '儲存中...' : '儲存個人設定' }}
          </button>
        </section>

        <!-- 房間設定 -->
        <section v-if="sessionStore.currentRoom" class="settings-section">
          <h2>🏠 房間設定</h2>
          
          <div class="setting-item">
            <label class="setting-label">
              房間名稱
            </label>
            <input 
              v-model="localRoomName"
              type="text" 
              class="setting-input"
              placeholder="房間名稱"
            />
          </div>
          
          <div class="setting-item">
            <label class="setting-label">
              主板預設語言
            </label>
            <select v-model="localBoardLang" class="setting-select">
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
            </select>
            <p class="setting-description">
              主板上顯示的預設語言，可針對特定講者覆寫
            </p>
          </div>
          
          <button @click="saveRoomSettings" :disabled="saving" class="save-btn">
            {{ saving ? '儲存中...' : '儲存房間設定' }}
          </button>
        </section>

        <!-- 講者語言覆寫設定 -->
        <section v-if="sessionStore.currentRoom" class="settings-section">
          <h2>🎯 講者語言覆寫</h2>
          <p class="section-description">
            為特定講者設定主板顯示語言，覆寫預設語言設定
          </p>
          
          <div class="overrides-list">
            <div 
              v-for="(override, index) in localOverrides" 
              :key="index"
              class="override-item"
            >
              <div class="override-inputs">
                <input
                  v-model="override.speakerName"
                  type="text"
                  placeholder="講者名稱或ID"
                  class="override-input"
                />
                <select v-model="override.targetLang" class="override-select">
                  <option value="">選擇語言</option>
                  <option value="zh-TW">繁體中文</option>
                  <option value="zh-CN">簡體中文</option>
                  <option value="en">English</option>
                  <option value="ja">日本語</option>
                  <option value="ko">한국어</option>
                  <option value="es">Español</option>
                  <option value="fr">Français</option>
                  <option value="de">Deutsch</option>
                </select>
                <button @click="removeOverride(index)" class="remove-btn">
                  🗑️
                </button>
              </div>
            </div>
            
            <button @click="addOverride" class="add-btn">
              + 新增覆寫規則
            </button>
          </div>
          
          <button @click="saveOverrides" :disabled="saving" class="save-btn">
            {{ saving ? '儲存中...' : '儲存覆寫設定' }}
          </button>
        </section>

        <!-- 系統資訊 -->
        <section class="settings-section">
          <h2>ℹ️ 系統資訊</h2>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">連線狀態</span>
              <span :class="['info-value', { connected: sessionStore.isConnected }]">
                {{ sessionStore.isConnected ? '已連線' : '未連線' }}
              </span>
            </div>
            <div class="info-item" v-if="sessionStore.currentRoom">
              <span class="info-label">房間 ID</span>
              <span class="info-value">{{ sessionStore.currentRoom.id }}</span>
            </div>
            <div class="info-item" v-if="sessionStore.user">
              <span class="info-label">使用者 ID</span>
              <span class="info-value">{{ sessionStore.user.id }}</span>
            </div>
          </div>
        </section>

        <!-- 危險操作 -->
        <section class="settings-section danger-section">
          <h2>⚠️ 危險操作</h2>
          <div class="danger-actions">
            <button @click="clearMessages" class="danger-btn">
              清除所有訊息
            </button>
            <button @click="logout" class="danger-btn">
              登出並清除資料
            </button>
          </div>
        </section>

      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { roomApi } from '../api/http'

const router = useRouter()
const sessionStore = useSessionStore()

// 本地狀態
const saving = ref(false)

// 個人設定
const localUserName = ref('')
const localUserLang = ref('zh-TW')

// 房間設定
const localRoomName = ref('')
const localBoardLang = ref('en')

// 覆寫設定
const localOverrides = ref<Array<{ speakerName: string; targetLang: string; speakerId?: string }>>([])

onMounted(() => {
  loadCurrentSettings()
})

function loadCurrentSettings() {
  // 載入個人設定
  if (sessionStore.user) {
    localUserName.value = sessionStore.user.displayName
    localUserLang.value = sessionStore.user.preferredLang
  }
  
  // 載入房間設定
  if (sessionStore.currentRoom) {
    localRoomName.value = sessionStore.currentRoom.name
    localBoardLang.value = sessionStore.currentRoom.defaultBoardLang
    
    // 載入覆寫設定
    localOverrides.value = sessionStore.currentRoom.overrides.map(override => ({
      speakerName: override.speakerId, // 這裡應該要轉換成名稱
      targetLang: override.targetLang,
      speakerId: override.speakerId
    }))
  }
}

async function savePersonalSettings() {
  if (!sessionStore.user) return
  
  saving.value = true
  try {
    // 更新偏好語言
    if (localUserLang.value !== sessionStore.user.preferredLang) {
      await roomApi.updateUserLang(sessionStore.user.id, localUserLang.value)
      sessionStore.updateUserLang(localUserLang.value)
    }
    
    // TODO: 更新顯示名稱的 API
    
    alert('個人設定已儲存')
  } catch (error) {
    console.error('Save personal settings failed:', error)
    alert('儲存失敗，請重試')
  } finally {
    saving.value = false
  }
}

async function saveRoomSettings() {
  if (!sessionStore.currentRoom) return
  
  saving.value = true
  try {
    // 更新主板語言
    if (localBoardLang.value !== sessionStore.currentRoom.defaultBoardLang) {
      await roomApi.updateBoardLang(sessionStore.currentRoom.id, localBoardLang.value)
      sessionStore.currentRoom.defaultBoardLang = localBoardLang.value
    }
    
    // TODO: 更新房間名稱的 API
    
    alert('房間設定已儲存')
  } catch (error) {
    console.error('Save room settings failed:', error)
    alert('儲存失敗，請重試')
  } finally {
    saving.value = false
  }
}

async function saveOverrides() {
  if (!sessionStore.currentRoom) return
  
  saving.value = true
  try {
    const validOverrides = localOverrides.value
      .filter(override => override.speakerName && override.targetLang)
      .map(override => ({
        speakerId: override.speakerId || override.speakerName, // 暫時用名稱作為 ID
        targetLang: override.targetLang
      }))
    
    await roomApi.updateOverrides(sessionStore.currentRoom.id, validOverrides)
    sessionStore.currentRoom.overrides = validOverrides
    
    alert('覆寫設定已儲存')
  } catch (error) {
    console.error('Save overrides failed:', error)
    alert('儲存失敗，請重試')
  } finally {
    saving.value = false
  }
}

function addOverride() {
  localOverrides.value.push({
    speakerName: '',
    targetLang: ''
  })
}

function removeOverride(index: number) {
  localOverrides.value.splice(index, 1)
}

function clearMessages() {
  if (confirm('確定要清除所有訊息嗎？此操作無法復原。')) {
    sessionStore.clearMessages()
    alert('訊息已清除')
  }
}

function logout() {
  if (confirm('確定要登出並清除所有本地資料嗎？')) {
    sessionStore.clearAuth()
    sessionStore.clearMessages()
    sessionStore.setWebSocket(null)
    router.push('/')
  }
}
</script>

<style scoped>
.settings-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.settings-header {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
}

.back-btn {
  background: none;
  border: 1px solid #667eea;
  color: #667eea;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s;
}

.back-btn:hover {
  background: #667eea;
  color: white;
}

.settings-header h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #333;
}

.settings-main {
  padding: 2rem;
}

.settings-content {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.settings-section {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 1rem;
  padding: 2rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.settings-section h2 {
  margin: 0 0 1.5rem 0;
  font-size: 1.3rem;
  color: #333;
}

.section-description {
  color: #666;
  margin-bottom: 1.5rem;
  line-height: 1.5;
}

.setting-item {
  margin-bottom: 1.5rem;
}

.setting-label {
  display: block;
  font-weight: 600;
  color: #333;
  margin-bottom: 0.5rem;
}

.setting-input, .setting-select {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #ddd;
  border-radius: 0.5rem;
  font-size: 1rem;
  transition: border-color 0.3s;
}

.setting-input:focus, .setting-select:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.setting-description {
  font-size: 0.9rem;
  color: #666;
  margin-top: 0.5rem;
  line-height: 1.4;
}

.save-btn {
  background: #667eea;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.save-btn:hover:not(:disabled) {
  background: #5a6fd8;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.overrides-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.override-item {
  border: 1px solid #e9ecef;
  border-radius: 0.5rem;
  padding: 1rem;
}

.override-inputs {
  display: grid;
  grid-template-columns: 1fr 200px 40px;
  gap: 1rem;
  align-items: center;
}

.override-input, .override-select {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 0.375rem;
  font-size: 0.9rem;
}

.remove-btn {
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 0.375rem;
  width: 32px;
  height: 32px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.add-btn {
  background: #28a745;
  color: white;
  border: none;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
}

.info-grid {
  display: grid;
  gap: 1rem;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  background: #f8f9fa;
  border-radius: 0.5rem;
}

.info-label {
  font-weight: 500;
  color: #333;
}

.info-value {
  font-family: monospace;
  color: #666;
  font-size: 0.9rem;
}

.info-value.connected {
  color: #28a745;
  font-weight: 600;
}

.danger-section {
  border: 2px solid #dc3545;
  background: rgba(220, 53, 69, 0.05);
}

.danger-actions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.danger-btn {
  background: #dc3545;
  color: white;
  border: none;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.danger-btn:hover {
  background: #c82333;
}

/* 響應式設計 */
@media (max-width: 768px) {
  .settings-header {
    padding: 1rem;
  }
  
  .settings-main {
    padding: 1rem;
  }
  
  .settings-section {
    padding: 1.5rem;
  }
  
  .override-inputs {
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }
  
  .danger-actions {
    flex-direction: column;
  }
}
</style>