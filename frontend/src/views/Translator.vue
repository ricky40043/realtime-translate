<template>
  <main class="translator-page">
    <section class="translator-card">
      <header class="page-header">
        <div class="logo" aria-hidden="true">🌍</div>
        <h1>雙向翻譯機</h1>
        <p>選擇兩種語言後，翻譯結果會固定顯示在上方</p>
      </header>

      <section v-if="results.length" class="results" aria-live="polite">
        <h2>最新翻譯</h2>
        <article class="result-card latest-result">
          <div class="result-row">
            <span class="result-label">原文</span>
            <p>{{ results[0].value.transcript }}</p>
          </div>
          <div class="result-meta">
            <span>偵測語言：{{ languageName(results[0].value.detected_lang) }}</span>
            <span>信心度：{{ Math.round(results[0].value.confidence * 100) }}%</span>
          </div>
          <div class="result-row translation-row">
            <span class="result-label">翻譯結果</span>
            <p>{{ results[0].value.translated_text }}</p>
          </div>
          <p class="direction">{{ languageName(results[0].value.source_lang) }} → {{ languageName(results[0].value.target_lang) }}</p>
        </article>
        <details v-if="results.length > 1" class="history">
          <summary>查看先前翻譯（{{ results.length - 1 }}）</summary>
          <article v-for="item in results.slice(1)" :key="item.id" class="result-card">
            <div class="result-row"><span class="result-label">原文</span><p>{{ item.value.transcript }}</p></div>
            <div class="result-row translation-row"><span class="result-label">翻譯結果</span><p>{{ item.value.translated_text }}</p></div>
          </article>
        </details>
      </section>

      <button class="settings-toggle" type="button" @click="settingsOpen = !settingsOpen">
        <span>翻譯設定</span><span aria-hidden="true">{{ settingsOpen ? '⌃' : '⌄' }}</span>
      </button>

      <div v-if="settingsOpen" class="settings-panel">
      <div class="language-grid">
        <label class="language-field">
          <span>語言 A</span>
          <select v-model="langA" :disabled="isRecording || isSubmitting">
            <option v-for="language in languages" :key="language.code" :value="language.code">
              {{ language.name }}
            </option>
          </select>
        </label>
        <div class="swap-icon" aria-hidden="true">↔</div>
        <label class="language-field">
          <span>語言 B</span>
          <select v-model="langB" :disabled="isRecording || isSubmitting">
            <option v-for="language in languages" :key="language.code" :value="language.code">
              {{ language.name }}
            </option>
          </select>
        </label>
      </div>

      <p v-if="sameLanguage" class="field-error">請選擇兩種不同的語言。</p>
      </div>

      <p class="live-hint">{{ isRecording ? '正在即時辨識，每 3 秒更新一次翻譯' : '開始後會持續翻譯，按停止即可結束' }}</p>

      <button
        class="record-button"
        :class="{ recording: isRecording }"
        :disabled="!authReady || (!isRecording && isSubmitting) || sameLanguage"
        type="button"
        @click="toggleRecording"
      >
        <span class="record-icon" aria-hidden="true">{{ isRecording ? '■' : '●' }}</span>
        <span v-if="isRecording">停止錄音</span>
        <span v-else-if="isSubmitting">翻譯中…</span>
        <span v-else-if="!authReady">準備中…</span>
        <span v-else>開始錄音</span>
      </button>
      <p class="record-hint">{{ isRecording ? '再次按下按鈕即可送出這段錄音' : '請在安靜環境中清楚說話' }}</p>

    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { authApi } from '../api/http'
import { speechApi, type TranslatorResponse } from '../api/speech'
import { useSessionStore } from '../stores/session'

const languages = [
  { code: 'zh-TW', name: '繁體中文' },
  { code: 'zh-CN', name: '简体中文' },
  { code: 'en', name: 'English' },
  { code: 'ms', name: 'Bahasa Melayu' },
  { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' },
  { code: 'th', name: 'ไทย' },
  { code: 'vi', name: 'Tiếng Việt' },
  { code: 'id', name: 'Bahasa Indonesia' },
  { code: 'es', name: 'Español' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'it', name: 'Italiano' },
  { code: 'pt', name: 'Português' },
  { code: 'ru', name: 'Русский' },
  { code: 'ar', name: 'العربية' },
  { code: 'hi', name: 'हिन्दी' },
  { code: 'nl', name: 'Nederlands' },
  { code: 'tr', name: 'Türkçe' },
]

const sessionStore = useSessionStore()
const langA = ref('zh-TW')
const langB = ref('en')
const settingsOpen = ref(true)
const authReady = ref(false)
const isRecording = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')
const permissionMessage = ref('')
const results = ref<Array<{ id: number; value: TranslatorResponse }>>([])
const mediaRecorder = ref<MediaRecorder | null>(null)
let mediaStream: MediaStream | null = null
let uploadChain: Promise<void> = Promise.resolve()
let resultId = 0
let segmentChunks: Blob[] = []
let segmentTimer: number | null = null
let stoppingForSegment = false

const sameLanguage = computed(() => langA.value === langB.value)

onMounted(async () => {
  sessionStore.loadAuth()
  if (!sessionStore.isAuthenticated) {
    try {
      const response = await authApi.guestLogin(
        `用戶_${Math.random().toString(36).slice(2, 8)}`,
        langA.value,
        langA.value,
        langB.value,
      )
      sessionStore.setAuth({
        id: response.user_id,
        displayName: response.display_name,
        preferredLang: response.preferred_lang,
        inputLang: response.input_lang,
        outputLang: response.output_lang,
      }, response.token)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '登入失敗，無法使用翻譯功能'
      return
    }
  }
  authReady.value = true
})

onBeforeUnmount(() => {
  if (isRecording.value) stopRecording()
  else stopMediaStream()
})

async function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else {
    await startRecording()
  }
}

async function startRecording() {
  errorMessage.value = ''
  permissionMessage.value = ''
  errorMessage.value = ''

  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    permissionMessage.value = '此瀏覽器不支援錄音功能，請改用最新版 Chrome、Safari 或 Edge。'
    return
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
      .find(type => MediaRecorder.isTypeSupported(type))
    isRecording.value = true
    settingsOpen.value = false
    startSegmentRecorder(mimeType)
    segmentTimer = window.setInterval(() => rotateSegment(mimeType), 3000)
  } catch (error) {
    stopMediaStream()
    permissionMessage.value = error instanceof DOMException && error.name === 'NotAllowedError'
      ? '請允許瀏覽器使用麥克風後再試一次。'
      : '無法啟用麥克風，請確認裝置與瀏覽器權限。'
  }
}

function startSegmentRecorder(mimeType?: string) {
  if (!mediaStream) return
  const recorder = mimeType ? new MediaRecorder(mediaStream, { mimeType }) : new MediaRecorder(mediaStream)
  segmentChunks = []
  recorder.ondataavailable = event => {
    if (event.data.size > 0) segmentChunks.push(event.data)
  }
  recorder.onstop = () => {
    const blob = new Blob(segmentChunks, { type: recorder.mimeType || 'audio/webm' })
    segmentChunks = []
    if (blob.size > 0) {
      uploadChain = uploadChain.then(() => submitRecording(blob)).catch(() => undefined)
    }
    if (stoppingForSegment) {
      stoppingForSegment = false
      isRecording.value = false
      stopMediaStream()
    } else if (isRecording.value) {
      startSegmentRecorder(mimeType)
    }
  }
  recorder.start()
  mediaRecorder.value = recorder
}

function rotateSegment(mimeType?: string) {
  if (!isRecording.value || !mediaRecorder.value || mediaRecorder.value.state === 'inactive') return
  stoppingForSegment = false
  mediaRecorder.value.stop()
}

function stopRecording() {
  if (segmentTimer !== null) {
    window.clearInterval(segmentTimer)
    segmentTimer = null
  }
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    stoppingForSegment = true
    mediaRecorder.value.stop()
  } else {
    isRecording.value = false
    stopMediaStream()
  }
}

function stopMediaStream() {
  mediaStream?.getTracks().forEach(track => track.stop())
  mediaStream = null
}

async function submitRecording(audioBlob: Blob) {
  if (sameLanguage.value) return
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    const translated = await speechApi.translate(audioBlob, langA.value, langB.value)
    results.value.unshift({ id: ++resultId, value: translated })
    if (results.value.length > 50) results.value.shift()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '翻譯失敗，請稍後再試。'
  } finally {
    isSubmitting.value = false
  }
}

function languageName(code: string): string {
  const family = code.toLowerCase().split('-')[0]
  return languages.find(language => language.code.toLowerCase().split('-')[0] === family)?.name || code
}
</script>

<style scoped>
.translator-page {
  min-height: 100vh;
  min-height: 100dvh;
  padding: 1rem;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  overflow-y: auto;
  background: linear-gradient(160deg, #0f0c29 0%, #302b63 52%, #24243e 100%);
  color: #fff;
}

.translator-card {
  width: min(100%, 560px);
  padding: clamp(1.25rem, 5vw, 2.5rem);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.08);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(16px);
}

.page-header { text-align: center; }
.logo { font-size: 3rem; line-height: 1; margin-bottom: .75rem; }
h1 { margin: 0; font-size: clamp(1.7rem, 7vw, 2.4rem); }
.page-header p { margin: .6rem 0 1.75rem; color: rgba(255, 255, 255, .68); }
.settings-toggle { width: 100%; display: flex; justify-content: space-between; padding: .8rem 0; border: 0; border-bottom: 1px solid rgba(255,255,255,.14); background: transparent; color: #fff; font-size: 1rem; font-weight: 700; }
.settings-panel { padding-top: 1rem; }
.live-hint { margin: 1rem 0 0; color: rgba(255, 255, 255, .62); text-align: center; font-size: .85rem; }

.language-grid { display: grid; grid-template-columns: 1fr auto 1fr; gap: .7rem; align-items: end; }
.language-field { display: flex; flex-direction: column; gap: .4rem; font-size: .9rem; font-weight: 600; }
select { width: 100%; min-height: 48px; padding: .7rem .75rem; border: 1px solid rgba(255, 255, 255, .2); border-radius: 10px; background: #252145; color: #fff; font-size: 1rem; }
.swap-icon { padding-bottom: .8rem; color: #c4b5fd; font-size: 1.4rem; }
.field-error { margin: .7rem 0 0; color: #fda4af; font-size: .9rem; text-align: center; }

.record-button { width: 100%; min-height: 68px; margin-top: 1.75rem; border: 0; border-radius: 16px; background: linear-gradient(135deg, #8b5cf6, #3b82f6); color: #fff; font-size: 1.2rem; font-weight: 700; }
.record-button:hover:not(:disabled) { filter: brightness(1.1); }
.record-button.recording { background: linear-gradient(135deg, #ef4444, #db2777); }
.record-icon { margin-right: .55rem; font-size: 1.1rem; }
.record-hint { min-height: 1.5em; margin: .7rem 0 1.2rem; color: rgba(255, 255, 255, .58); text-align: center; font-size: .85rem; }
.status { margin: 1rem 0; padding: .8rem 1rem; border-radius: 10px; text-align: center; }
.status.error { background: rgba(244, 63, 94, .16); color: #fecdd3; }

.result-card { margin-top: 1.25rem; padding: 1.1rem; border-radius: 14px; background: rgba(15, 23, 42, .42); }
.results { margin-top: 1.4rem; }
.results h2 { margin: 0; font-size: 1.1rem; }
.result-row { display: grid; gap: .4rem; }
.result-row p { margin: 0; font-size: 1.1rem; line-height: 1.6; overflow-wrap: anywhere; }
.result-label { color: #c4b5fd; font-size: .82rem; font-weight: 700; }
.result-meta { display: flex; flex-wrap: wrap; gap: .8rem; margin: .8rem 0 1rem; color: rgba(255, 255, 255, .58); font-size: .8rem; }
.translation-row { padding-top: 1rem; border-top: 1px solid rgba(255, 255, 255, .12); }
.direction { margin: .9rem 0 0; color: #93c5fd; text-align: right; font-size: .82rem; }

@media (max-width: 420px) {
  .translator-page { padding: .65rem; align-items: flex-start; }
  .translator-card { margin-top: 1rem; border-radius: 18px; }
  .language-grid { grid-template-columns: 1fr; gap: .65rem; }
  .swap-icon { padding: 0; text-align: center; transform: rotate(90deg); }
}
</style>
