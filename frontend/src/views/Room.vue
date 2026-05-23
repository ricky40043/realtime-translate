<template>
  <div class="home">
    <header class="home-header">
      <div class="logo">🌍</div>
      <h1>多語言即時翻譯</h1>
      <p>語音即時翻譯，多語言無障礙溝通</p>
    </header>

    <main class="home-main">
      <!-- 個人設定 -->
      <section class="card profile-card">
        <div class="field">
          <label>你的名稱</label>
          <input
            v-model="displayName"
            @input="saveProfile"
            placeholder="輸入你的名稱"
            class="input-field"
            type="text"
            autocomplete="nickname"
          />
        </div>
        <div class="field">
          <label>我說的語言</label>
          <select v-model="inputLang" @change="saveProfile" class="select-field">
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
            <option value="my">မြန်မာ</option>
            <option value="id">Bahasa Indonesia</option>
            <option value="ms">Bahasa Melayu</option>
            <option value="yue">廣東話</option>
          </select>
        </div>
      </section>

      <!-- 建立房間 -->
      <section class="card create-card">
        <button @click="createRoom" :disabled="isLoading" class="btn-create">
          <span v-if="isLoading">⏳ 建立中...</span>
          <span v-else>🚀 建立房間</span>
        </button>
        <p class="hint">成為主持人，邀請他人加入翻譯</p>
      </section>

      <div class="divider"><span>或</span></div>

      <!-- 加入房間 -->
      <section class="card join-card">
        <label>加入現有房間</label>
        <div class="join-row">
          <input
            v-model="joinCode"
            placeholder="輸入房間代碼"
            class="input-field"
            type="text"
            @keyup.enter="joinRoom"
          />
          <button @click="joinRoom" :disabled="!joinCode.trim() || isLoading" class="btn-join">
            加入
          </button>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { authApi, roomApi } from '../api/http'

const router = useRouter()
const sessionStore = useSessionStore()

const displayName = ref('')
const inputLang = ref('zh-TW')
const joinCode = ref('')
const isLoading = ref(false)
const authReady = ref(false)

onMounted(async () => {
  sessionStore.loadAuth()
  loadProfile()
  // 首頁每次都重新登入，避免 localStorage 殘留的過期 token 導致 401
  try {
    await performGuestLogin()
    authReady.value = true
  } catch (error) {
    console.error('初始化登入失敗:', error)
    authReady.value = false
  }
})

function loadProfile() {
  const saved = localStorage.getItem('userProfile')
  if (!saved) return
  const p = safeParseJson<{ displayName?: string; inputLang?: string }>(saved, {})
  displayName.value = p.displayName || ''
  inputLang.value = p.inputLang || 'zh-TW'
}

function safeParseJson<T>(value: string | null, fallback: T): T {
  if (!value) return fallback
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

function saveProfile() {
  localStorage.setItem('userProfile', JSON.stringify({
    displayName: displayName.value,
    inputLang: inputLang.value
  }))
}

async function performGuestLogin() {
  const name = displayName.value.trim() || `用戶_${Math.random().toString(36).substr(2, 6)}`
  const response = await authApi.guestLogin(name, inputLang.value, inputLang.value, 'zh-TW')
  sessionStore.setAuth({
    id: response.user_id,
    displayName: response.display_name,
    preferredLang: response.preferred_lang,
    inputLang: response.input_lang,
    outputLang: response.output_lang
  }, response.token)
}

function isMobileDevice(): boolean {
  return window.innerWidth < 768 || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
}

function isEmbeddedBrowser(): boolean {
  return /Line|FBAN|FBAV|Instagram|MicroMessenger/i.test(navigator.userAgent)
}

async function createRoom() {
  if (isLoading.value) return
  isLoading.value = true

  // iOS Safari：window.open 必須在任何 await 之前同步執行，否則會被攔截
  // 手機版：新分頁開說話視窗，當前頁留在白板
  let speakerTab: Window | null = null
  if (isMobileDevice() && !isEmbeddedBrowser()) {
    speakerTab = window.open('', '_blank')
  }

  try {
    saveProfile()

    if (!sessionStore.isAuthenticated || !authReady.value) {
      await performGuestLogin()
      authReady.value = true
    }

    const savedAdvanced = localStorage.getItem('userAdvancedSettings')
    const advancedSettings = safeParseJson<{ outputLang?: string }>(savedAdvanced, {})
    const boardLang = advancedSettings.outputLang || 'zh-TW'

    const now = new Date()
    const roomName = `房間_${(now.getMonth()+1).toString().padStart(2,'0')}${now.getDate().toString().padStart(2,'0')}_${now.getHours().toString().padStart(2,'0')}${now.getMinutes().toString().padStart(2,'0')}`
    const response = await roomApi.createRoom(roomName, boardLang)

    const userLink = `${window.location.origin}/user?roomId=${response.id}`

    if (isMobileDevice()) {
      // 新分頁進入說話模式（帶 share=true 自動展開分享面板）
      if (speakerTab) {
        speakerTab.location.href = `${userLink}&share=true`
      }
      // 自動複製加入連結到剪貼簿，方便分享給別人
      try {
        navigator.clipboard?.writeText(userLink).catch(() => {})
      } catch {
        // 部分瀏覽器限制剪貼簿，靜默失敗
      }
      // 當前頁進入白板
      router.push(`/host/${response.id}`)
    } else {
      // 桌面版：直接進入白板
      if (speakerTab) speakerTab.close()
      router.push(`/host/${response.id}`)
    }
  } catch (error) {
    console.error('創建房間失敗:', error)
    if (speakerTab) speakerTab.close()
    alert('創建房間失敗，請重試')
  } finally {
    isLoading.value = false
  }
}

async function joinRoom() {
  const code = joinCode.value.trim()
  if (!code) return
  router.push(`/user?roomId=${code}`)
}
</script>

<style scoped>
.home {
  min-height: 100vh;
  min-height: 100dvh;
  background: linear-gradient(160deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 1rem 2rem;
}

.home-header {
  text-align: center;
  color: white;
  padding: 2.5rem 1rem 1.5rem;
}

.logo {
  font-size: 3.5rem;
  margin-bottom: 0.5rem;
}

h1 {
  font-size: 1.9rem;
  font-weight: 700;
  margin: 0 0 0.5rem;
  background: linear-gradient(90deg, #a78bfa, #60a5fa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.home-header p {
  color: rgba(255, 255, 255, 0.55);
  font-size: 0.95rem;
  margin: 0;
}

.home-main {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.card {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  padding: 1.25rem;
  backdrop-filter: blur(12px);
}

.profile-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.field label,
.join-card label {
  color: rgba(255, 255, 255, 0.65);
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.input-field {
  width: 100%;
  padding: 0.8rem 1rem;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 10px;
  color: white;
  font-size: 1rem;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}

.input-field::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.input-field:focus {
  border-color: #a78bfa;
  box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.15);
}

.select-field {
  width: 100%;
  padding: 0.8rem 2.5rem 0.8rem 1rem;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 10px;
  color: white;
  font-size: 1rem;
  outline: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='rgba(255,255,255,0.5)' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 1rem center;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.select-field:focus {
  border-color: #a78bfa;
}

.select-field option {
  background: #302b63;
  color: white;
}

.create-card {
  text-align: center;
}

.btn-create {
  width: 100%;
  padding: 1.05rem;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 1.1rem;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  letter-spacing: 0.02em;
}

.btn-create:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.45);
}

.btn-create:active:not(:disabled) {
  transform: translateY(0);
}

.btn-create:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.hint {
  margin: 0.65rem 0 0;
  color: rgba(255, 255, 255, 0.4);
  font-size: 0.8rem;
}

.divider {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: rgba(255, 255, 255, 0.28);
  font-size: 0.85rem;
  padding: 0 0.5rem;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, 0.12);
}

.join-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.join-row {
  display: flex;
  gap: 0.6rem;
}

.join-row .input-field {
  flex: 1;
}

.btn-join {
  padding: 0.8rem 1.25rem;
  background: rgba(255, 255, 255, 0.12);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}

.btn-join:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.22);
}

.btn-join:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
