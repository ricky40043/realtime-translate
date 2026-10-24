<template>
  <main class="translator-page">
    <header class="top-bar">
      <h1>雙向翻譯機</h1>
      <div class="top-right">
      <p v-if="quota" class="quota" title="Groq 今天剩餘可呼叫次數，每分鐘更新">
        語音剩 {{ quotaText(quota.speech) }} · 翻譯剩 {{ quotaText(quota.translate) }}
      </p>
      <button class="pair-chip" type="button" :disabled="sameLanguage" @click="settingsOpen = !settingsOpen">
        {{ languageName(langA) }} ⇄ {{ languageName(langB) }}
        <span aria-hidden="true">{{ settingsOpen ? '⌃' : '⌄' }}</span>
      </button>
      </div>
    </header>

    <div v-if="settingsOpen" class="settings-panel">
      <label class="language-field">
        <span>語言 A</span>
        <select v-model="langA">
          <option v-for="language in languages" :key="language.code" :value="language.code">{{ language.name }}</option>
        </select>
      </label>
      <button class="swap-button" type="button" aria-label="交換語言" @click="swapLanguages">⇄</button>
      <label class="language-field">
        <span>語言 B</span>
        <select v-model="langB">
          <option v-for="language in languages" :key="language.code" :value="language.code">{{ language.name }}</option>
        </select>
      </label>
      <p v-if="sameLanguage" class="field-error">請選擇兩種不同的語言。</p>
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
        <span>{{ speaking ? '偵測到說話' : '聆聽中' }}{{ slowMode ? '（額度有限，預覽放慢）' : '' }}</span>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { authApi } from '../api/http'
import { speechApi, type QuotaInfo, type TranslatorResponse } from '../api/speech'
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
const langA = ref('zh-TW')
const langB = ref('en')
const settingsOpen = ref(true)
const authReady = ref(false)
const isRecording = ref(false)
const speaking = ref(false)
const level = ref(0)
const slowMode = ref(false)
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

const sameLanguage = computed(() => langA.value === langB.value)
const visibleEntries = computed(() => entries.value.filter(e => entryTranscript(e)))

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
  refreshQuota()
  quotaTimer = window.setInterval(refreshQuota, 60_000)
})

onBeforeUnmount(() => {
  stopRecording()
  if (quotaTimer !== null) window.clearInterval(quotaTimer)
})

async function refreshQuota() {
  try { quota.value = await speechApi.quota() } catch { /* 查不到就維持上一次的數字 */ }
}

function quotaText(info: QuotaInfo | null): string {
  return info ? info.remaining.toLocaleString() : '—'
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
    isRecording.value = true
    lastActivityAt = performance.now() / 1000
    settingsOpen.value = false
    requestWakeLock()
  } catch (error) {
    teardownAudio()
    permissionMessage.value = error instanceof DOMException && error.name === 'NotAllowedError'
      ? '請允許瀏覽器使用麥克風後再試一次。'
      : '無法啟用麥克風，請確認裝置與瀏覽器權限。'
  }
}

function stopRecording() {
  if (isRecording.value && voicedSec >= MIN_VOICE_SEC) sendFinal(blocks.length, true)
  else endEntry()
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
  const voicedRaw = calibrated && db > floor + (inSpeech ? KEEP_MARGIN_DB : START_MARGIN_DB) && db > -55
  recentVoiced.push(voicedRaw)
  if (recentVoiced.length > 3) recentVoiced.shift()
  const voiced = recentVoiced.filter(Boolean).length >= 2
  if (voiced) inSpeech = true
  speechRunSec = inSpeech ? speechRunSec + blockSec : 0

  speaking.value = inSpeech
  level.value = Math.max(0, Math.min(1, (db - floor) / 30))

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
  const wav = encodeWav(blocks)
  speechApi.translate(wav, langA.value, langB.value, { isFinal: false })
    .then(result => {
      interimInterval = Math.max(MIN_INTERVAL, interimInterval * 0.9)
      slowMode.value = interimInterval > 2
      if (target.final || seq < target.interimSeq || result.status !== 'ok' || !result.transcript) return
      target.interimSeq = seq
      lastActivityAt = performance.now() / 1000
      target.transcript = result.transcript
      target.translation = result.translated_text
      placePiece(owner, target, result)
      scrollToBottom()
    })
    .catch((error: any) => {
      // 免費額度每分鐘次數有限：被擋就放慢預覽，定稿仍會照常送
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
  submitFinal(wav, levels, owner, target, 0).finally(() => { pendingFinals-- })
}

async function submitFinal(wav: Blob, levels: number[], owner: Entry, target: Piece, attempt: number): Promise<void> {
  try {
    // 不把前一段文字當提示給 Whisper：換人講另一種語言時，提示會把新的話硬轉成前一種語言
    const result = await speechApi.translate(wav, langA.value, langB.value, { isFinal: true })
    target.final = true
    if (result.status === 'ok' && result.transcript) {
      lastActivityAt = performance.now() / 1000
      target.transcript = result.transcript
      target.translation = result.translated_text
      owner = placePiece(owner, target, result)
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
    if (error?.status === 429 && attempt < 4) {
      await new Promise(resolve => setTimeout(resolve, 1500 * (attempt + 1)))
      return submitFinal(wav, levels, owner, target, attempt + 1)
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
  return sameFamily(code, langA.value)
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
function encodeWav(segment: Block[]): Blob {
  const inputRate = audioContext?.sampleRate || 48000
  const total = segment.reduce((sum, b) => sum + b.data.length, 0)
  const input = new Float32Array(total)
  let offset = 0
  for (const b of segment) {
    input.set(b.data, offset)
    offset += b.data.length
  }
  const ratio = inputRate / TARGET_SAMPLE_RATE
  const outLength = Math.floor(total / ratio)
  const view = new DataView(new ArrayBuffer(44 + outLength * 2))
  const writeStr = (pos: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(pos + i, str.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + outLength * 2, true)
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
  view.setUint32(40, outLength * 2, true)
  for (let i = 0; i < outLength; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(total, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    const sample = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)))
    view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
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
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  padding: .75rem max(1rem, calc((100% - 720px) / 2)) 0;
  background: linear-gradient(160deg, #0f0c29 0%, #302b63 52%, #24243e 100%);
  color: #fff;
}

.top-bar { display: flex; align-items: center; justify-content: space-between; gap: .75rem; padding-bottom: .6rem; }
h1 { margin: 0; font-size: 1.15rem; }
.top-right { display: flex; flex-direction: column; align-items: flex-end; gap: .25rem; }
.quota { margin: 0; color: rgba(255,255,255,.5); font-size: .7rem; white-space: nowrap; }
.pair-chip { display: flex; gap: .4rem; align-items: center; padding: .45rem .8rem; border: 1px solid rgba(255,255,255,.2); border-radius: 999px; background: rgba(255,255,255,.08); color: #fff; font-size: .9rem; }

.settings-panel { display: grid; grid-template-columns: 1fr auto 1fr; gap: .6rem; align-items: end; padding: .8rem; margin-bottom: .6rem; border-radius: 14px; background: rgba(255,255,255,.08); }
.language-field { display: flex; flex-direction: column; gap: .35rem; font-size: .85rem; font-weight: 600; }
select { width: 100%; min-height: 44px; padding: .55rem .7rem; border: 1px solid rgba(255,255,255,.2); border-radius: 10px; background: #252145; color: #fff; font-size: 1rem; }
.swap-button { min-height: 44px; padding: 0 .8rem; border: 0; border-radius: 10px; background: rgba(196,181,253,.15); color: #c4b5fd; font-size: 1.3rem; }
.field-error { grid-column: 1 / -1; margin: 0; color: #fda4af; font-size: .9rem; text-align: center; }

.conversation { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: .8rem; padding: .4rem 0 1rem; }
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
