<template>
  <main class="translator-page">
    <header class="top-bar">
      <h1>雙向翻譯機</h1>
      <div class="top-right">
      <p v-if="quota" class="quota" title="Groq 剩餘可呼叫次數，每次翻譯後更新">
        語音剩 {{ quotaText(quota.speech) }} · 翻譯剩 {{ quotaText(quota.translate) }}
      </p>
      <button class="pair-chip" type="button" :disabled="sameLanguage" @click="settingsOpen = !settingsOpen">
        <span class="pair-text">{{ sideLabel(langA) }} ⇄ {{ sideLabel(langB) }}</span>
        <span aria-hidden="true">{{ settingsOpen ? '⌃' : '⌄' }}</span>
      </button>
      </div>
    </header>

    <div v-if="settingsOpen" class="settings-panel">
      <template v-for="(side, sideIndex) in sides" :key="side.key">
      <button v-if="sideIndex === 1" class="swap-button" type="button" aria-label="交換語言" @click="swapLanguages">⇄</button>
      <div class="language-field">
        <span>語言 {{ side.key }}<small v-if="sideIndex === 0">每邊可多選；講這邊任一種語言，都翻成另一邊的「主要」語言（第一個）</small></span>
        <div class="lang-chips">
          <span v-for="(code, index) in side.list.value" :key="code" class="lang-chip" :class="{ primary: index === 0 }">
            <select class="chip-select" :value="code" :aria-label="`語言 ${side.key} 第 ${index + 1} 個`" @change="replaceLang(side.list, code, $event)">
              <option v-for="language in optionsFor(side.list.value, code)" :key="language.code" :value="language.code">{{ language.name }}</option>
            </select>
            <em v-if="index === 0 && side.list.value.length > 1" class="primary-tag">主要</em>
            <button v-else-if="index > 0" type="button" class="make-primary" @click="makePrimary(side.list, code)">設為主要</button>
            <button v-if="side.list.value.length > 1" type="button" class="chip-remove" :aria-label="`移除${languageName(code)}`" @click="removeLang(side.list, code)">×</button>
          </span>
          <select class="add-lang" :value="''" @change="addLang(side.list, $event)">
            <option value="" disabled>＋ 加語言</option>
            <option v-for="language in availableFor(side.list.value)" :key="language.code" :value="language.code">{{ language.name }}</option>
          </select>
        </div>
      </div>
      </template>
      <div class="model-fields">
        <label class="model-field">
          <span>語音辨識</span>
          <select v-model="sttModel">
            <option v-for="m in modelOptions.stt" :key="m.id" :value="m.id" :disabled="!m.available">{{ m.label }}{{ m.available ? '' : '（未設定）' }}</option>
          </select>
        </label>
        <label class="model-field">
          <span>翻譯模型</span>
          <select v-model="translateModel">
            <option v-for="m in modelOptions.translate" :key="m.id" :value="m.id" :disabled="!m.available">{{ m.label }}{{ m.available ? '' : '（未設定）' }}</option>
          </select>
        </label>
        <small v-if="isLocal">本機模型不需要網路；第一次使用要等模型載入（約 10–30 秒）。</small>
      </div>
      <p v-if="sameLanguage" class="field-error">A、B 兩邊不能有同一種語言（{{ overlapName }}）。</p>
    </div>

    <section ref="conversationEl" class="conversation" aria-live="polite" @scroll="onConversationScroll">
      <p v-if="!visibleEntries.length" class="empty-hint">
        {{ isRecording ? '請開始說話，翻譯會即時出現在這裡' : '按下「開始翻譯」後直接說話，不用每句按按鈕' }}
      </p>
      <article
        v-for="entry in visibleEntries"
        :key="entry.id"
        class="entry"
        :class="[entry.sourceLang ? (isSideA(entry.sourceLang) ? 'side-a' : 'side-b') : 'side-a', { live: !isDone(entry) }]"
      >
        <p class="translation">{{ entryTranslation(entry) || '…' }}</p>
        <p class="original">
          <span v-if="entry.sourceLang" class="lang-badge">{{ languageName(entry.sourceLang) }} → {{ languageName(entry.targetLang) }}</span>
          <span>{{ entryTranscript(entry) }}</span>
        </p>
      </article>
    </section>

    <footer class="controls">
      <p v-if="errorMessage" class="status error">{{ errorMessage }}</p>
      <p v-if="permissionMessage" class="status error">{{ permissionMessage }}</p>
      <p v-if="noticeMessage && !isRecording" class="status notice">{{ noticeMessage }}</p>
      <div v-if="isRecording" class="listen-status">
        <div class="level-bar"><div class="level-fill" :class="{ speaking }" :style="{ width: `${Math.round(level * 100)}%` }"></div></div>
        <span>{{ speaking ? '偵測到說話' : '聆聽中' }}{{ slowNetwork ? '（網路較慢，翻譯會延遲）' : slowMode ? '（額度有限，預覽放慢）' : '' }}</span>
        <span v-if="debug" class="debug">{{ debugText }}</span>
      </div>
      <button
        class="record-button"
        :class="{ recording: isRecording }"
        :disabled="!authReady || sameLanguage"
        type="button"
        @click="toggleRecording"
      >
        <span class="record-icon" aria-hidden="true">{{ isRecording ? '■' : '●' }}</span>
        <span v-if="isRecording">停止翻譯</span>
        <span v-else-if="!authReady">準備中…</span>
        <span v-else>開始翻譯</span>
      </button>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { Mp3Encoder } from '@breezystack/lamejs'
import { authApi } from '../api/http'
import { speechApi, type ModelOption, type QuotaInfo, type TranslatorResponse } from '../api/speech'
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

// 連續收音：一直錄，用「有沒有人講話」決定一句話的開始和結束，不再每 3 秒硬切
const BLOCK_SIZE = 2048
const TARGET_SAMPLE_RATE = 16000
const MP3_KBPS = 32
const SLOW_NETWORK_SEC = 4     // 一句定稿來回超過這麼久，提示網路慢
const PREROLL_SEC = 0.3        // 開口前保留的聲音，避免第一個字被切掉
const PAUSE_SEC = 0.7          // 停頓多久算一句講完
const MAX_PIECE_SEC = 8        // 一直講不停時，最長多久先定稿一段
const CUT_SEARCH_SEC = 2       // 在最後幾秒內找最安靜的地方切
const MIN_VOICE_SEC = 0.25     // 有說話的長度不到這個就當雜音
// 判斷有沒有人講話：背景音量取「沒人講話時」最近 6 秒的中位數，
// 開口要比背景大 12 dB，講話中只要大 6 dB 就算還在講（離手機近的人才會觸發，遠處人聲不會）
const NOISE_WINDOW_SEC = 6
const START_MARGIN_DB = 12
const KEEP_MARGIN_DB = 6
const CALIBRATE_SEC = 0.5      // 剛開始先聽一下背景
const STUCK_SPEECH_SEC = 15    // 「一直在講」太久，多半是背景變大聲了，背景重新算
// iPhone 開了降噪後收音很小聲（講話常只有 -50 dB 上下），絕對門檻放低，主要靠「比背景大多少」判斷
const MIN_DB = -72
const MIN_INTERVAL = 1.0       // 講話中多久更新一次預覽（秒），被限速時自動放慢
const MAX_INTERVAL = 4.0
const AUTO_STOP_SEC = 10       // 這麼久沒有翻出任何東西（沒人講話或只有背景聲）就自動停止，避免一直耗用額度

interface Piece {
  id: number
  transcript: string
  translation: string
  final: boolean
  sent: boolean            // 定稿已送出，等結果中
  interimSeq: number       // 已套用的預覽序號，舊的回應不能蓋掉新的
}
interface Entry {
  id: number
  pieces: Piece[]
  sourceLang: string
  targetLang: string
  ended: boolean           // 這句已經講完（停頓）
}
interface Block { data: Float32Array; db: number; voiced: boolean }

const sessionStore = useSessionStore()
// 每一邊可以多選；第一個是「主要」語言，另一邊講的話都翻成它
const langA = ref<string[]>(loadLangs('translatorLangA', ['zh-TW']))
const langB = ref<string[]>(loadLangs('translatorLangB', ['en']))
const sides = [{ key: 'A', list: langA }, { key: 'B', list: langB }]
// 模型：groq = 雲端；local:… / ollama:… = 這台電腦上的本機模型（不需要網路）
const modelOptions = ref<{ stt: ModelOption[]; translate: ModelOption[] }>({
  stt: [{ id: 'groq', label: 'Groq Whisper（雲端）', available: true }],
  translate: [{ id: 'groq', label: 'Groq（雲端）', available: true }],
})
const sttModel = ref(loadSetting('translatorSttModel', 'groq'))
const translateModel = ref(loadSetting('translatorTranslateModel', 'groq'))
const isLocal = computed(() => sttModel.value.startsWith('local:') || translateModel.value.startsWith('ollama:'))
const settingsOpen = ref(true)
const authReady = ref(false)
const isRecording = ref(false)
const speaking = ref(false)
const level = ref(0)
const slowMode = ref(false)
const slowNetwork = ref(false)
// 網址加 ?debug=1 顯示音量數字，現場調整用
const debug = new URLSearchParams(location.search).has('debug')
const debugText = ref('')
let requestCount = 0
const errorMessage = ref('')
const permissionMessage = ref('')
const noticeMessage = ref('')
const quota = ref<{ speech: QuotaInfo | null; translate: QuotaInfo | null } | null>(null)
let quotaTimer: number | null = null
const entries = ref<Entry[]>([])
const conversationEl = ref<HTMLElement | null>(null)

let stream: MediaStream | null = null
let audioContext: AudioContext | null = null
let sourceNode: MediaStreamAudioSourceNode | null = null
let processor: ScriptProcessorNode | null = null
let wakeLock: any = null
let blockSec = BLOCK_SIZE / 48000
let levelHistory: number[] = []
let recentVoiced: boolean[] = []
let inSpeech = false
let speechRunSec = 0

let blocks: Block[] = []       // 目前這一段（尚未定稿）的聲音
let voicedSec = 0              // 這一段裡有說話的長度
let silenceSec = 0             // 連續沒說話的長度
let entry: Entry | null = null // 正在講的這一句
let piece: Piece | null = null // 這一句目前還沒定稿的那一段
let interimInterval = MIN_INTERVAL
let lastInterimAt = 0
let lastInterimVoiced = 0
let interimInFlight = false
let interimSeq = 0
let nextId = 0
let followBottom = true
let lastActivityAt = 0         // 開始錄音或最後一次翻出內容的時間
let pendingFinals = 0
// 每次開始／停止就換一個編號：停止前送出、停止後才回來的結果不再顯示
let runId = 0

const overlap = computed(() => langA.value.find(a => langB.value.some(b => sameFamily(a, b))) || '')
const overlapName = computed(() => languageName(overlap.value))
const sameLanguage = computed(() => !!overlap.value)
watch(langA, v => saveLangs('translatorLangA', v), { deep: true })
watch(langB, v => saveLangs('translatorLangB', v), { deep: true })
watch(sttModel, v => saveSetting('translatorSttModel', v))
watch(translateModel, v => saveSetting('translatorTranslateModel', v))
watch([sttModel, translateModel], () => { if (authReady.value) refreshQuota() })  // 換模型就顯示那個模型的剩餘次數
const visibleEntries = computed(() => entries.value.filter(e => entryTranscript(e)))

onMounted(async () => {
  sessionStore.loadAuth()
  if (!sessionStore.isAuthenticated && !(await guestLogin())) return
  authReady.value = true
  loadModels()
  refreshQuota()
  quotaTimer = window.setInterval(refreshQuota, 60_000)
})

onBeforeUnmount(() => {
  stopRecording()
  if (quotaTimer !== null) window.clearInterval(quotaTimer)
})

async function refreshQuota() {
  try { quota.value = await speechApi.quota(modelChoice()) } catch (error: any) {
    // 查不到就維持上一次的數字；憑證過期就重新登入
    if (error?.status === 401 && await guestLogin()) quota.value = await speechApi.quota(modelChoice()).catch(() => quota.value)
  }
}

// 每次翻譯的回應都帶著最新剩餘次數，直接更新；沒在講話時靠每分鐘查一次
function applyQuota(result: TranslatorResponse) {
  if (result.quota?.speech || result.quota?.translate) quota.value = result.quota
}

function quotaText(info: QuotaInfo | null): string {
  return info ? info.remaining.toLocaleString() : '—'
}

// 用訪客身分登入；登入憑證過期（7 天）時也用這個重新拿一張
let loginPromise: Promise<boolean> | null = null
function guestLogin(): Promise<boolean> {
  loginPromise ??= (async () => {
    try {
      const response = await authApi.guestLogin(
        `用戶_${Math.random().toString(36).slice(2, 8)}`,
        langA.value[0],
        langA.value[0],
        langB.value[0],
      )
      sessionStore.setAuth({
        id: response.user_id,
        displayName: response.display_name,
        preferredLang: response.preferred_lang,
        inputLang: response.input_lang,
        outputLang: response.output_lang,
      }, response.token)
      errorMessage.value = ''
      return true
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '登入失敗，無法使用翻譯功能'
      return false
    } finally {
      loginPromise = null
    }
  })()
  return loginPromise
}

async function loadModels() {
  try {
    const options = await speechApi.models()
    modelOptions.value = options
    // 記住的模型不在了（換電腦、模型刪掉）或雲端沒設定：改用第一個能用的
    const pick = (list: ModelOption[], current: string) =>
      list.find(m => m.id === current && m.available)?.id || list.find(m => m.available)?.id || current
    sttModel.value = pick(options.stt, sttModel.value)
    translateModel.value = pick(options.translate, translateModel.value)
  } catch { /* 讀不到就維持雲端 */ }
}

function modelChoice() {
  return {
    sttModel: sttModel.value === 'groq' ? '' : sttModel.value,
    translateModel: translateModel.value === 'groq' ? '' : translateModel.value,
  }
}

function loadSetting(key: string, fallback: string): string {
  try { return localStorage.getItem(key) || fallback } catch { return fallback }
}

function saveSetting(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* 存不了也沒關係 */ }
}

function loadLangs(key: string, fallback: string[]): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null')
    if (Array.isArray(saved) && saved.length && saved.every(c => languages.some(l => l.code === c))) return saved
  } catch { /* 讀不到就用預設 */ }
  return fallback
}

function saveLangs(key: string, value: string[]) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* 存不了也沒關係 */ }
}

function sideLabel(list: string[]): string {
  return list.map(languageName).join('、')
}

function availableFor(list: string[]) {
  return languages.filter(language => !list.includes(language.code))
}

function addLang(list: Ref<string[]>, event: Event) {
  const select = event.target as HTMLSelectElement
  if (select.value && !list.value.includes(select.value)) list.value = [...list.value, select.value]
  select.value = ''
}

// 每個語言都可以直接點開換成別的（選單裡不列同一邊已經選的）
function optionsFor(list: string[], current: string) {
  return languages.filter(language => language.code === current || !list.includes(language.code))
}

function replaceLang(list: Ref<string[]>, code: string, event: Event) {
  const value = (event.target as HTMLSelectElement).value
  list.value = list.value.map(c => (c === code ? value : c))
}

function removeLang(list: Ref<string[]>, code: string) {
  if (list.value.length > 1) list.value = list.value.filter(c => c !== code)
}

function makePrimary(list: Ref<string[]>, code: string) {
  list.value = [code, ...list.value.filter(c => c !== code)]
}

function swapLanguages() {
  ;[langA.value, langB.value] = [langB.value, langA.value]
}

async function toggleRecording() {
  if (isRecording.value) stopRecording()
  else await startRecording()
}

async function startRecording() {
  errorMessage.value = ''
  permissionMessage.value = ''
  noticeMessage.value = ''
  const Ctx = window.AudioContext || (window as any).webkitAudioContext
  if (!navigator.mediaDevices?.getUserMedia || !Ctx) {
    permissionMessage.value = '此瀏覽器不支援錄音功能，請改用最新版 Chrome、Safari 或 Edge。'
    return
  }

  try {
    // 在點擊事件中建立 AudioContext（iOS 需要使用者手勢）
    audioContext = new Ctx()
    if (audioContext.state === 'suspended') await audioContext.resume()
    // 瀏覽器內建降噪：展場背景聲會先被壓低
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    sourceNode = audioContext.createMediaStreamSource(stream)
    processor = audioContext.createScriptProcessor(BLOCK_SIZE, 1, 1)
    processor.onaudioprocess = onAudioBlock
    sourceNode.connect(processor)
    processor.connect(audioContext.destination)  // 輸出全是 0；不接 destination 不會觸發

    blockSec = BLOCK_SIZE / audioContext.sampleRate
    levelHistory = []
    recentVoiced = []
    inSpeech = false
    speechRunSec = 0
    resetPiece()
    entry = null
    interimInterval = MIN_INTERVAL
    slowMode.value = false
    runId++
    isRecording.value = true
    lastActivityAt = performance.now() / 1000
    settingsOpen.value = false
    testNetwork()
    requestWakeLock()
  } catch (error) {
    teardownAudio()
    permissionMessage.value = error instanceof DOMException && error.name === 'NotAllowedError'
      ? '請允許瀏覽器使用麥克風後再試一次。'
      : '無法啟用麥克風，請確認裝置與瀏覽器權限。'
  }
}

// 按停止就立刻停：還沒講完的那句不送出，還在路上的翻譯回來也不顯示；畫面上已經有的字保留
function stopRecording() {
  runId++
  for (const e of entries.value) for (const p of e.pieces) p.final = true
  resetPiece()
  endEntry()
  for (const e of [...entries.value]) pruneEntry(e)
  isRecording.value = false
  teardownAudio()
}

function teardownAudio() {
  if (processor) {
    processor.onaudioprocess = null
    processor.disconnect()
  }
  sourceNode?.disconnect()
  audioContext?.close().catch(() => {})
  stream?.getTracks().forEach(track => track.stop())
  processor = null
  sourceNode = null
  audioContext = null
  stream = null
  speaking.value = false
  level.value = 0
  wakeLock?.release?.().catch(() => {})
  wakeLock = null
}

async function requestWakeLock() {
  // 展場長時間使用：錄音中不讓螢幕自動關掉
  try { wakeLock = await (navigator as any).wakeLock?.request('screen') } catch { wakeLock = null }
}

function onAudioBlock(event: AudioProcessingEvent) {
  if (!isRecording.value) return
  if (performance.now() / 1000 - lastActivityAt > AUTO_STOP_SEC && pendingFinals === 0 && !interimInFlight) {
    stopRecording()
    noticeMessage.value = `${AUTO_STOP_SEC} 秒沒有聲音，已自動停止。按「開始翻譯」繼續。`
    return
  }
  const data = new Float32Array(event.inputBuffer.getChannelData(0))
  let sum = 0
  for (let i = 0; i < data.length; i++) sum += data[i] * data[i]
  const db = 20 * Math.log10(Math.sqrt(sum / data.length) + 1e-9)

  // 背景音量跟著環境自動調整（展場持續的吵雜聲會被當成背景）；講話中不更新，不然講越久越聽不到
  if (!inSpeech || speechRunSec > STUCK_SPEECH_SEC) addBackground([db])
  const sorted = [...levelHistory].sort((a, b) => a - b)
  const floor = sorted[Math.floor(sorted.length * 0.5)]
  const calibrated = levelHistory.length * blockSec >= CALIBRATE_SEC
  const voicedRaw = calibrated && db > floor + (inSpeech ? KEEP_MARGIN_DB : START_MARGIN_DB) && db > MIN_DB
  recentVoiced.push(voicedRaw)
  if (recentVoiced.length > 3) recentVoiced.shift()
  const voiced = recentVoiced.filter(Boolean).length >= 2
  if (voiced) inSpeech = true
  speechRunSec = inSpeech ? speechRunSec + blockSec : 0

  speaking.value = inSpeech
  level.value = Math.max(0, Math.min(1, (db - floor) / 30))
  if (debug) debugText.value = `${Math.round(db)}dB 背景${Math.round(floor ?? 0)} 已送${requestCount} ${lastFormat} ${uploadBps ? (uploadBps / 1e6).toFixed(1) + 'Mbps' : ''}`

  blocks.push({ data, db, voiced })
  if (voiced) {
    voicedSec += blockSec
    silenceSec = 0
  } else {
    silenceSec += blockSec
  }

  if (voicedSec < MIN_VOICE_SEC) {
    // 還沒開口：只留一小段前導音；這句之前有講過、停頓夠久就算講完
    if (voicedSec === 0 || silenceSec >= PAUSE_SEC) {
      const keep = Math.ceil(PREROLL_SEC / blockSec)
      if (blocks.length > keep) blocks.splice(0, blocks.length - keep)
      voicedSec = 0
      if (silenceSec >= PAUSE_SEC) {
        inSpeech = false
        endEntry()
      }
    }
    return
  }

  ensureEntry()
  if (silenceSec >= PAUSE_SEC) {
    // 停頓 → 這句講完
    inSpeech = false
    sendFinal(blocks.length, true)
  } else if (blocks.length * blockSec >= MAX_PIECE_SEC) {
    // 一直講不停：在最後兩秒內最安靜的地方切開，前面先定稿，同一句繼續
    const search = Math.max(1, Math.round(CUT_SEARCH_SEC / blockSec))
    let cut = blocks.length
    let quietest = Infinity
    for (let i = blocks.length - 1; i >= Math.max(1, blocks.length - search); i--) {
      if (blocks[i].db < quietest) {
        quietest = blocks[i].db
        cut = i + 1
      }
    }
    sendFinal(cut, false)
  } else {
    maybeSendInterim()
  }
}

function addBackground(levels: number[]) {
  levelHistory.push(...levels)
  const max = Math.round(NOISE_WINDOW_SEC / blockSec)
  if (levelHistory.length > max) levelHistory.splice(0, levelHistory.length - max)
}

function ensureEntry() {
  if (!entry || entry.ended) {
    entry = { id: ++nextId, pieces: [], sourceLang: '', targetLang: '', ended: false }
    entries.value.push(entry)
    if (entries.value.length > 100) entries.value.shift()
    entry = entries.value[entries.value.length - 1]  // 用 reactive 版本，之後改動才會更新畫面
    scrollToBottom()
  }
  if (!piece) {
    entry.pieces.push({ id: ++nextId, transcript: '', translation: '', final: false, sent: false, interimSeq: 0 })
    piece = entry.pieces[entry.pieces.length - 1]
  }
}

function resetPiece() {
  blocks = []
  voicedSec = 0
  silenceSec = 0
  piece = null
  lastInterimVoiced = 0
}

function endEntry() {
  if (entry) {
    entry.ended = true
    pruneEntry(entry)
  }
  entry = null
}

// 講話中：每隔一段時間把「這一段到目前為止的聲音」送去，畫面上的字一直長出來
function maybeSendInterim() {
  const now = performance.now() / 1000
  if (interimInFlight || !entry || !piece) return
  if (now - lastInterimAt < interimInterval) return
  if (voicedSec < 0.6) return                       // 太短的聲音 Whisper 容易亂猜
  if (voicedSec - lastInterimVoiced < 0.3) return  // 上次之後沒有新的話
  lastInterimAt = now
  lastInterimVoiced = voicedSec
  interimInFlight = true

  const target = piece
  const owner = entry
  const seq = ++interimSeq
  const run = runId
  const wav = encodeWav(blocks)
  requestCount++
  timedTranslate(wav, false)
    .then(result => {
      applyQuota(result)
      if (run !== runId) return
      interimInterval = Math.max(MIN_INTERVAL, interimInterval * 0.9)
      // 本機模型比較慢（沒有顯卡時一句要好幾秒）：預覽間隔跟著拉長，不要把定稿卡在後面排隊
      if ((result.server_ms ?? 0) > 1000) interimInterval = Math.min(8, Math.max(interimInterval, (result.server_ms! / 1000) * 1.5))
      slowMode.value = interimInterval > 2
      if (target.final || seq < target.interimSeq || result.status !== 'ok' || !result.transcript) return
      target.interimSeq = seq
      lastActivityAt = performance.now() / 1000
      target.transcript = result.transcript
      // 本機模型忙的時候預覽只有原文、沒有翻譯：保留上一次的翻譯
      target.translation = result.translated_text || target.translation
      placePiece(owner, target, result)
      scrollToBottom()
    })
    .catch((error: any) => {
      // 免費額度每分鐘次數有限：被擋就放慢預覽，定稿仍會照常送
      if (error?.status === 401) guestLogin()
      if (error?.status === 429) {
        interimInterval = Math.min(MAX_INTERVAL, interimInterval * 1.5)
        slowMode.value = interimInterval > 2
      }
    })
    .finally(() => { interimInFlight = false })
}

// 定稿：送出前 n 個區塊。endsEntry=true 代表講完一句；false 代表講太長先切一段
function sendFinal(n: number, endsEntry: boolean) {
  if (!entry || !piece) return
  const target = piece
  const owner = entry
  const wav = encodeWav(blocks.slice(0, n))
  const levels = blocks.slice(0, n).map(b => b.db)
  target.sent = true

  const rest = blocks.slice(n)
  resetPiece()
  if (endsEntry) {
    endEntry()
  } else {
    blocks = rest
    voicedSec = rest.filter(b => b.voiced).length * blockSec
  }

  pendingFinals++
  submitFinal(wav, levels, owner, target, 0, runId).finally(() => { pendingFinals-- })
}

async function submitFinal(wav: Blob, levels: number[], owner: Entry, target: Piece, attempt: number, run: number): Promise<void> {
  try {
    // 不把前一段文字當提示給 Whisper：換人講另一種語言時，提示會把新的話硬轉成前一種語言
    requestCount++
    const sentAt = performance.now()
    const slowTimer = window.setTimeout(() => { slowNetwork.value = true }, SLOW_NETWORK_SEC * 1000)
    const result = await timedTranslate(wav, true)
    window.clearTimeout(slowTimer)
    slowNetwork.value = performance.now() - sentAt > SLOW_NETWORK_SEC * 1000
    applyQuota(result)
    if (run !== runId) return
    target.final = true
    if (result.status === 'ok' && result.transcript) {
      lastActivityAt = performance.now() / 1000
      target.transcript = result.transcript
      target.translation = result.translated_text
      owner = placePiece(owner, target, result)
      // 兩個人接著講（插話）被拆成好幾段：後面的段落各自放在新的對話框
      let previous = target
      for (const segment of result.segments?.slice(1) || []) {
        owner = ownerOf(previous, owner)
        owner.pieces.splice(owner.pieces.indexOf(previous) + 1, 0, {
          id: ++nextId, transcript: segment.transcript, translation: segment.translated_text,
          final: true, sent: true, interimSeq: 0,
        })
        previous = owner.pieces[owner.pieces.indexOf(previous) + 1]
        owner = placePiece(owner, previous, { ...result, ...segment })
      }
    } else {
      // 辨識不出話（或是旁邊的人講別的語言）：這段其實是背景聲，音量算進背景，之後才不會一直被當成有人講話
      if (isRecording.value) addBackground(levels)
      if (!target.transcript || result.status === 'other_lang') {
        target.transcript = ''
        target.translation = ''
      }
    }
    // 定稿沒結果但預覽有字：保留預覽，不讓講過的話消失
    pruneEntry(ownerOf(target, owner))
    scrollToBottom()
  } catch (error: any) {
    if (run !== runId) return
    if (error?.status === 401 && attempt < 1 && await guestLogin()) {
      return submitFinal(wav, levels, owner, target, attempt + 1, run)
    }
    if (error?.status === 429 && attempt < 4) {
      await new Promise(resolve => setTimeout(resolve, 1500 * (attempt + 1)))
      return submitFinal(wav, levels, owner, target, attempt + 1, run)
    }
    target.final = true
    pruneEntry(ownerOf(target, owner))
    if (!target.transcript) errorMessage.value = error instanceof Error ? error.message : '翻譯失敗，請稍後再試。'
  }
}

// 決定這段話放在哪一句：語言和這句不同，代表換另一個人講了（展場吵雜時常常聽不出停頓），
// 從這段開始拆成新的一句。回傳這段最後所屬的句子。
function placePiece(owner: Entry, target: Piece, result: TranslatorResponse): Entry {
  errorMessage.value = ''
  owner = ownerOf(target, owner)
  const index = owner.pieces.indexOf(target)
  const earlier = owner.pieces.slice(0, index).some(p => p.transcript)
  if (!owner.sourceLang || !earlier) {
    // 這句的第一段（或前面都是雜音）：語言以這段為準
    owner.sourceLang = result.source_lang
    owner.targetLang = result.target_lang
    return owner
  }
  if (sameFamily(owner.sourceLang, result.source_lang)) return owner

  const moved = owner.pieces.splice(index)
  const split: Entry = { id: ++nextId, pieces: moved, sourceLang: result.source_lang, targetLang: result.target_lang, ended: owner.ended }
  owner.ended = true
  entries.value.splice(entries.value.findIndex(e => e.id === owner.id) + 1, 0, split)
  const created = entries.value.find(e => e.id === split.id)!
  if (entry && entry.id === owner.id) entry = created  // 還在講：後面的話接到新的這句
  pruneEntry(owner)
  return created
}

// 段落可能已經被拆到新的一句，找它現在所在的句子
function ownerOf(target: Piece, fallback: Entry): Entry {
  return entries.value.find(e => e.pieces.includes(target)) || fallback
}

function sameFamily(a: string, b: string): boolean {
  return a.toLowerCase().split('-')[0] === b.toLowerCase().split('-')[0]
}

// 講完、全部定稿、卻沒有任何字的句子（雜音）從畫面上拿掉
function pruneEntry(target: Entry) {
  if (!isDone(target) || entryTranscript(target)) return
  const index = entries.value.findIndex(e => e.id === target.id)
  if (index >= 0) entries.value.splice(index, 1)
}

function isDone(target: Entry): boolean {
  return target.ended && target.pieces.every(p => p.final)
}

const NO_SPACE = new Set(['zh', 'ja', 'th'])
function joinText(parts: string[], lang: string): string {
  const sep = NO_SPACE.has(lang.toLowerCase().split('-')[0]) ? '' : ' '
  return parts.filter(Boolean).join(sep)
}
function entryTranscript(target: Entry): string {
  return joinText(target.pieces.map(p => p.transcript), target.sourceLang)
}
function entryTranslation(target: Entry): string {
  return joinText(target.pieces.map(p => p.translation), target.targetLang)
}

function isSideA(code: string): boolean {
  return langA.value.some(a => sameFamily(code, a))
}

function onConversationScroll() {
  const el = conversationEl.value
  if (el) followBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollToBottom() {
  if (!followBottom) return
  nextTick(() => {
    const el = conversationEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 降到 16kHz 單聲道 16-bit WAV（Whisper 本來就用 16kHz，檔案也小）
// 上傳格式看網速決定：MP3 每秒約 4 KB、WAV 32 KB，但壓縮要花時間（手機上每秒語音約 10–25 ms）。
// 網路慢時壓縮省很多上傳時間；網路很快時不壓縮反而比較快。每次送出都重新估算網速。
let uploadBps = 0              // 估計的上傳速度（bit/s），0 = 還不知道
let baseLatencyMs = 0          // 網路來回的固定延遲
let encodeMsPerSec = 15        // 壓縮每秒語音要幾毫秒（實際量到後更新）
let lastFormat = ''

function encodeWav(segment: Block[]): Blob {
  const pcm = toPcm16k(segment)
  const sec = pcm.length / TARGET_SAMPLE_RATE
  let useMp3 = true            // 還沒量到網速：先壓縮比較保險
  if (uploadBps > 0) {
    const wavMs = (sec * TARGET_SAMPLE_RATE * 2 * 8 / uploadBps) * 1000
    const mp3Ms = (sec * MP3_KBPS * 1000 / uploadBps) * 1000 + encodeMsPerSec * sec
    useMp3 = mp3Ms < wavMs
  }
  if (useMp3) {
    try {
      const started = performance.now()
      const blob = encodeMp3(pcm)
      if (sec > 0.5) encodeMsPerSec = encodeMsPerSec * 0.7 + ((performance.now() - started) / sec) * 0.3
      lastFormat = 'MP3'
      return blob
    } catch { /* 壓縮失敗就送 WAV */ }
  }
  lastFormat = 'WAV'
  return pcmToWav(pcm)
}

// 送出並計時：來回時間扣掉伺服器處理時間和固定延遲，剩下的就是上傳花的時間
async function timedTranslate(blob: Blob, isFinal: boolean): Promise<TranslatorResponse> {
  const started = performance.now()
  const result = await speechApi.translate(blob, langA.value.join(','), langB.value.join(','), { isFinal, ...modelChoice() })
  const transferMs = performance.now() - started - (result.server_ms ?? 0) - baseLatencyMs
  if (result.server_ms != null && blob.size > 8000) updateUploadSpeed(blob.size, transferMs)
  return result
}

function updateUploadSpeed(bytes: number, transferMs: number) {
  const sample = (bytes * 8) / (Math.max(transferMs, 10) / 1000)
  uploadBps = uploadBps ? uploadBps * 0.7 + sample * 0.3 : sample
}

// 開始翻譯時先測一次網速（不用模型額度）：先量固定延遲，再傳 96 KB 量上傳速度
async function testNetwork() {
  try {
    const latency = Math.min(await speechApi.ping(0), await speechApi.ping(0))
    baseLatencyMs = latency
    const ms = await speechApi.ping(96 * 1024)
    updateUploadSpeed(96 * 1024, ms - latency)
  } catch { /* 測不到就先用壓縮 */ }
}

function toPcm16k(segment: Block[]): Int16Array {
  const inputRate = audioContext?.sampleRate || 48000
  const total = segment.reduce((sum, b) => sum + b.data.length, 0)
  const input = new Float32Array(total)
  let offset = 0
  for (const b of segment) {
    input.set(b.data, offset)
    offset += b.data.length
  }
  // 收音太小聲時先放大（最多 20 倍），Whisper 對小聲的話容易聽錯語言
  let peak = 0
  for (let i = 0; i < total; i++) peak = Math.max(peak, Math.abs(input[i]))
  const gain = peak > 0 ? Math.min(20, 0.9 / peak) : 1
  const ratio = inputRate / TARGET_SAMPLE_RATE
  const outLength = Math.floor(total / ratio)
  const out = new Int16Array(outLength)
  for (let i = 0; i < outLength; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(total, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    const sample = Math.max(-1, Math.min(1, (sum / Math.max(1, end - start)) * gain))
    out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return out
}

function encodeMp3(pcm: Int16Array): Blob {
  const encoder = new Mp3Encoder(1, TARGET_SAMPLE_RATE, MP3_KBPS)
  const chunks: Uint8Array[] = []
  for (let i = 0; i < pcm.length; i += 1152) {
    const out = encoder.encodeBuffer(pcm.subarray(i, i + 1152))
    if (out.length) chunks.push(new Uint8Array(out))
  }
  const tail = encoder.flush()
  if (tail.length) chunks.push(new Uint8Array(tail))
  return new Blob(chunks as BlobPart[], { type: 'audio/mpeg' })
}

function pcmToWav(pcm: Int16Array): Blob {
  const view = new DataView(new ArrayBuffer(44 + pcm.length * 2))
  const writeStr = (pos: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(pos + i, str.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + pcm.length * 2, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, TARGET_SAMPLE_RATE, true)
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeStr(36, 'data')
  view.setUint32(40, pcm.length * 2, true)
  for (let i = 0; i < pcm.length; i++) view.setInt16(44 + i * 2, pcm[i], true)
  return new Blob([view], { type: 'audio/wav' })
}

function languageName(code: string): string {
  if (!code) return ''
  const exact = languages.find(language => language.code.toLowerCase() === code.toLowerCase())
  if (exact) return exact.name
  const family = code.toLowerCase().split('-')[0]
  return languages.find(language => language.code.toLowerCase().split('-')[0] === family)?.name || code
}
</script>

<style scoped>
.translator-page {
  /* 釘在畫面上：手機在按鈕附近往上滑時，整頁不會被推上去、露出底下的白色 */
  position: fixed;
  inset: 0;
  overflow: hidden;
  overscroll-behavior: none;
  display: flex;
  flex-direction: column;
  padding: .75rem max(1rem, calc((100% - 720px) / 2)) 0;
  background: linear-gradient(160deg, #0f0c29 0%, #302b63 52%, #24243e 100%);
  color: #fff;
}

.top-bar { display: flex; align-items: center; justify-content: space-between; gap: .75rem; padding-bottom: .6rem; }
h1 { margin: 0; font-size: 1.15rem; white-space: nowrap; }
.top-right { min-width: 0; display: flex; flex-direction: column; align-items: flex-end; gap: .25rem; }
.quota { margin: 0; color: rgba(255,255,255,.5); font-size: .7rem; white-space: nowrap; }
.pair-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pair-chip { max-width: min(62vw, 420px); display: flex; gap: .4rem; align-items: center; padding: .45rem .8rem; border: 1px solid rgba(255,255,255,.2); border-radius: 999px; background: rgba(255,255,255,.08); color: #fff; font-size: .9rem; }

.settings-panel { max-height: 60%; overflow-y: auto; overscroll-behavior: contain; flex-shrink: 0; display: grid; grid-template-columns: 1fr; gap: .6rem; align-items: end; padding: .8rem; margin-bottom: .6rem; border-radius: 14px; background: rgba(255,255,255,.08); }
.language-field { display: flex; flex-direction: column; gap: .35rem; font-size: .85rem; font-weight: 600; }
select { width: 100%; min-height: 44px; padding: .55rem .7rem; border: 1px solid rgba(255,255,255,.2); border-radius: 10px; background: #252145; color: #fff; font-size: 1rem; }
.swap-button { justify-self: center; transform: rotate(90deg); min-height: 44px; padding: 0 .8rem; border: 0; border-radius: 10px; background: rgba(196,181,253,.15); color: #c4b5fd; font-size: 1.3rem; }
.language-field small { display: block; margin-top: .15rem; font-weight: 400; font-size: .72rem; opacity: .6; }
.lang-chips { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.lang-chip { display: inline-flex; align-items: center; border: 1px solid rgba(255,255,255,.2); border-radius: 999px; background: #252145; }
.lang-chip.primary { border-color: #a78bfa; background: rgba(167,139,250,.22); }
select.chip-select { width: auto; min-height: 38px; padding: 0 .2rem 0 .8rem; border: 0; border-radius: 999px; background: transparent; font-size: .95rem; }
.primary-tag { font-style: normal; font-size: .68rem; padding: .05rem .35rem; margin-right: .3rem; border-radius: 6px; background: #a78bfa; color: #1e1b4b; }
.make-primary { min-height: 38px; padding: 0 .3rem; border: 0; background: none; color: #c4b5fd; font-size: .72rem; }
.lang-chip:not(:has(.chip-remove)) { padding-right: .4rem; }
.chip-remove { min-width: 32px; min-height: 38px; border: 0; background: none; color: rgba(255,255,255,.6); font-size: 1.1rem; }
select.add-lang { width: auto; min-height: 38px; padding: 0 .6rem; border-style: dashed; border-radius: 999px; font-size: .9rem; }
.model-fields { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; padding-top: .4rem; border-top: 1px solid rgba(255,255,255,.1); }
.model-field { display: flex; flex-direction: column; gap: .35rem; font-size: .85rem; font-weight: 600; min-width: 0; }
.model-field select { font-size: .9rem; }
.model-fields small { grid-column: 1 / -1; font-size: .72rem; opacity: .65; }
@media (max-width: 480px) { .model-fields { grid-template-columns: 1fr; } }
.field-error { grid-column: 1 / -1; margin: 0; color: #fda4af; font-size: .9rem; text-align: center; }

.conversation { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; display: flex; flex-direction: column; gap: .8rem; padding: .4rem 0 1rem; }
.empty-hint { margin: auto; max-width: 18em; color: rgba(255,255,255,.55); text-align: center; line-height: 1.6; }

.entry { max-width: 88%; padding: .85rem 1rem; border-radius: 16px; background: rgba(15,23,42,.55); transition: opacity .2s; }
.entry.side-a { align-self: flex-start; border-bottom-left-radius: 4px; }
.entry.side-b { align-self: flex-end; border-bottom-right-radius: 4px; background: rgba(59,130,246,.22); }
.entry.live .translation { color: rgba(255,255,255,.72); }
.entry.live .translation::after { content: ' ▍'; color: #c4b5fd; animation: blink 1s steps(2) infinite; }
.translation { margin: 0; font-size: 1.45rem; font-weight: 600; line-height: 1.45; overflow-wrap: anywhere; }
.original { margin: .45rem 0 0; color: rgba(255,255,255,.58); font-size: .85rem; line-height: 1.5; overflow-wrap: anywhere; }
.lang-badge { display: inline-block; margin-right: .4rem; padding: 0 .4rem; border-radius: 6px; background: rgba(147,197,253,.16); color: #93c5fd; font-size: .72rem; }
@keyframes blink { 50% { opacity: 0; } }

.controls { padding: .6rem 0 calc(.8rem + env(safe-area-inset-bottom, 0px)); border-top: 1px solid rgba(255,255,255,.1); }
.listen-status { display: flex; align-items: center; gap: .6rem; margin-bottom: .55rem; color: rgba(255,255,255,.62); font-size: .8rem; }
.debug { font-size: .7rem; opacity: .7; margin-left: auto; font-variant-numeric: tabular-nums; }
.level-bar { flex: 0 0 72px; height: 6px; border-radius: 3px; background: rgba(255,255,255,.12); overflow: hidden; }
.level-fill { height: 100%; background: rgba(255,255,255,.4); transition: width .08s; }
.level-fill.speaking { background: #4ade80; }
.record-button { width: 100%; min-height: 60px; border: 0; border-radius: 16px; background: linear-gradient(135deg, #8b5cf6, #3b82f6); color: #fff; font-size: 1.15rem; font-weight: 700; }
.record-button:disabled { opacity: .55; }
.record-button.recording { background: linear-gradient(135deg, #ef4444, #db2777); }
.record-icon { margin-right: .5rem; }
.status { margin: 0 0 .55rem; padding: .6rem .8rem; border-radius: 10px; text-align: center; font-size: .9rem; }
.status.error { background: rgba(244,63,94,.16); color: #fecdd3; }
.status.notice { background: rgba(196,181,253,.14); color: #ddd6fe; }

@media (max-width: 480px) {
  .settings-panel { grid-template-columns: 1fr; }
  .swap-button { justify-self: center; transform: rotate(90deg); }
  .translation { font-size: 1.3rem; }
}
</style>
