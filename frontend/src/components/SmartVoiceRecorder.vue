<template>
  <div class="smart-voice-recorder">
    <button
      @click="toggleRecording"
      :class="['smart-record-btn', { 
        recording: isRecording, 
        processing: isProcessing,
        disabled: !isSupported || isProcessing 
      }]"
      :disabled="!isSupported || isProcessing"
    >
      <div class="btn-content">
        <div class="icon">
          <span v-if="!isRecording && !isProcessing">🎤</span>
          <span v-else-if="isProcessing">⏳</span>
          <div v-else class="recording-animation">
            <div class="pulse"></div>
            <span>🔴</span>
          </div>
        </div>
        <div class="text">
          <span v-if="!isSupported">不支援</span>
          <span v-else-if="isProcessing">處理中...</span>
          <span v-else-if="isRecording">
            {{ recordingMode === 'smart' ? '智能錄音中' : '手動錄音中' }} {{ formatTime(recordingTime) }}
            <br>
            <small>{{ vadStatus || '點擊可停止錄音' }}</small>
          </span>
          <span v-else>{{ recordingMode === 'manual' ? '點擊開始錄音' : '智能語音輸入' }}</span>
        </div>
      </div>
    </button>
    
    <!-- 智能檢測狀態指示器 -->
    <div v-if="isRecording" class="smart-indicator">
      <div class="volume-display">
        <div class="volume-bars">
          <div 
            v-for="i in 10" 
            :key="i"
            class="volume-bar"
            :class="{ 
              active: volumeLevel >= i,
              voice: isVoiceDetected && volumeLevel >= i,
              silence: !isVoiceDetected && volumeLevel >= i
            }"
          ></div>
        </div>
        <!-- <div class="threshold-line" :style="{ left: `${(settings.segmentThreshold / 30) * 100}%` }"></div> -->
      </div>
      
      <div class="vad-info">
        <div class="vad-status" :class="{ active: isVoiceDetected }">
          {{ isVoiceDetected ? '🎙️ 檢測到語音' : '🔇 靜音中' }}
        </div>
        <!-- <div class="silence-timer" v-if="!isVoiceDetected && silenceTimer > 0">
          靜音 {{ (settings.silenceTimeout - silenceTimer).toFixed(1) }}s
        </div>
        <div class="auto-stop-info" v-if="recordingTime >= settings.maxRecordingTime - 5">
          將在 {{ (settings.maxRecordingTime - recordingTime).toFixed(0) }}s 後自動結束
        </div> -->
      </div>
    </div>
    
    <!-- 錄音模式切換 -->
    <!-- <div class="mode-selector">
      <button 
        @click="recordingMode = 'smart'"
        :class="['mode-btn', { active: recordingMode === 'smart' }]"
      >
        🧠 智能模式
      </button>
      <button 
        @click="recordingMode = 'manual'"
        :class="['mode-btn', { active: recordingMode === 'manual' }]"
      >
        👆 手動模式
      </button>
    </div> -->
    
    <!-- 錯誤訊息 -->
    <div v-if="error" class="error-message">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { speechApi } from '../api/speech'

interface SmartSettings {
  segmentThreshold: number    // 語音檢測閾值（音量 %）
  silenceTimeout: number      // 多久沒聲音後自動結束錄音
  segmentDelay: number        // 停頓多久算一句講完（秒）
  maxSegmentTime?: number     // 一直講不停時，最長幾秒就先送出一段
}

interface Props {
  roomId: string
  disabled?: boolean
  userLang?: string
  settings: SmartSettings
  speakerName?: string
}

interface Emits {
  (e: 'transcript', result: { text: string; confidence: number; lang: string }): void
  (e: 'error', error: string): void
  (e: 'recording-start'): void
  (e: 'recording-end'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ── 分段即時翻譯 ──────────────────────────────────────────────
// 麥克風一直錄（不再停掉重開，不會漏字）：
//   1. 講話中每 maxSegmentTime 秒，把目前視窗「從頭到現在」的音訊整段送出
//      （is_final=false），後端重新辨識並取代上一次的結果，前面聽錯的字會被修正
//   2. 視窗超過 WINDOW_MAX_SEC 秒，在最後一秒內最安靜的地方切開開新視窗（window+1），
//      舊視窗的文字就定下來，避免每次上傳的音檔越來越長
//   3. 停頓 segmentDelay 秒 → 這句講完，整個視窗再送一次定稿（is_final=true）
// 同一句話共用 utterance_id，並且依序上傳，保證順序正確。
const DEFAULT_MAX_SEGMENT_SEC = 3
const WINDOW_MAX_SEC = 9
const CUT_WINDOW_SEC = 1.0     // 切視窗時，在最後這段時間內找最安靜的切點
const PREROLL_SEC = 0.3        // 開口前保留的音，避免第一個字被切掉
const MIN_VOICE_SEC = 0.3      // 新的一句至少要有這麼長的人聲才送（濾掉雜音）
const TARGET_SAMPLE_RATE = 16000
const BLOCK_SIZE = 2048

const isSupported = ref(false)
const isRecording = ref(false)
const isProcessing = ref(false)
const recordingTime = ref(0)
const volumeLevel = ref(0)
const error = ref('')
const recordingMode = ref<'smart' | 'manual'>('smart')
const isVoiceDetected = ref(false)
const vadStatus = ref('等待語音...')

interface Block { data: Float32Array; vol: number; voiced: boolean }

let stream: MediaStream | null = null
let audioContext: AudioContext | null = null
let sourceNode: MediaStreamAudioSourceNode | null = null
let analyser: AnalyserNode | null = null
let processor: ScriptProcessorNode | null = null
let freqData: Uint8Array<ArrayBuffer> | null = null
let volumeSamples: number[] = []

let blocks: Block[] = []       // 目前視窗的音訊
let sentBlocks = 0            // 上次送出時視窗有幾個區塊
let windowIndex = 0
let blockSec = BLOCK_SIZE / 48000
let hasVoice = false          // 目前視窗裡有沒有人聲
let silenceSec = 0            // 連續靜音秒數
let utteranceId = newUtteranceId()
let utteranceStarted = false  // 這句已經送出過被切開的前半段
let uploadChain: Promise<void> = Promise.resolve()

onMounted(() => {
  isSupported.value = !!(navigator.mediaDevices?.getUserMedia && (window.AudioContext || (window as any).webkitAudioContext))
})

onUnmounted(() => {
  teardownAudio()
  stream?.getTracks().forEach(track => track.stop())
  stream = null
})

function newUtteranceId(): string {
  return (crypto as any).randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

const maxSegmentSec = () => props.settings.maxSegmentTime || DEFAULT_MAX_SEGMENT_SEC
const pauseSec = () => props.settings.segmentDelay || 0.6

async function toggleRecording() {
  if (isRecording.value) {
    await stopRecording()
  } else {
    await startRecording()
  }
}

async function startRecording() {
  try {
    error.value = ''
    // 在點擊事件中建立 AudioContext（iOS 需要使用者手勢）
    const Ctx = window.AudioContext || (window as any).webkitAudioContext
    audioContext = new Ctx()
    if (audioContext.state === 'suspended') await audioContext.resume()

    if (!stream || stream.getAudioTracks().every(t => t.readyState === 'ended')) {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      })
    }

    sourceNode = audioContext.createMediaStreamSource(stream)
    analyser = audioContext.createAnalyser()
    analyser.fftSize = 256
    analyser.smoothingTimeConstant = 0.8
    freqData = new Uint8Array(analyser.frequencyBinCount)
    processor = audioContext.createScriptProcessor(BLOCK_SIZE, 1, 1)
    processor.onaudioprocess = onAudioBlock
    sourceNode.connect(analyser)
    sourceNode.connect(processor)
    processor.connect(audioContext.destination)  // 輸出全是 0，不會有回音；不接 destination 不會觸發

    blockSec = BLOCK_SIZE / audioContext.sampleRate
    volumeSamples = []
    resetUtterance()
    recordingTime.value = 0
    isRecording.value = true
    vadStatus.value = '等待語音...'
    emit('recording-start')
  } catch (err) {
    console.error('錄音失敗:', err)
    error.value = '無法存取麥克風，請檢查權限設定'
    teardownAudio()
  }
}

function onAudioBlock(event: AudioProcessingEvent) {
  if (!isRecording.value || !analyser || !freqData) return

  // 音量計算方式與舊版相同，使用者原本調好的閾值不用改
  analyser.getByteFrequencyData(freqData)
  const average = freqData.reduce((sum, v) => sum + v, 0) / freqData.length
  volumeSamples.push(Math.min(100, (average / 255) * 100))
  if (volumeSamples.length > 5) volumeSamples.shift()
  const vol = volumeSamples.reduce((sum, v) => sum + v, 0) / volumeSamples.length
  const voiced = vol > props.settings.segmentThreshold

  volumeLevel.value = Math.min(10, Math.floor(vol / 10))
  isVoiceDetected.value = voiced
  recordingTime.value += blockSec

  blocks.push({ data: new Float32Array(event.inputBuffer.getChannelData(0)), vol, voiced })
  if (voiced) {
    hasVoice = true
    silenceSec = 0
  } else {
    silenceSec += blockSec
  }

  if (!hasVoice) {
    // 還沒開口：只保留一小段前導音
    const keep = Math.ceil(PREROLL_SEC / blockSec)
    if (blocks.length > keep) blocks.splice(0, blocks.length - keep)
    sentBlocks = 0
    // 前一個視窗已送出、之後就沒再講話：通知後端這句結束
    if (utteranceStarted && silenceSec >= pauseSec()) {
      finishUtterance()
    }
  } else if (silenceSec >= pauseSec()) {
    // 停頓 → 這句講完，整個視窗送一次定稿（句尾的靜音不裁掉，輕聲的尾音常被當成靜音）
    sendWindow(blocks.length, true)
  } else if ((blocks.length - sentBlocks) * blockSec >= maxSegmentSec()) {
    if (blocks.length * blockSec >= WINDOW_MAX_SEC) {
      // 視窗太長：在最後一秒內找最安靜的地方切開，前面定下來，後面開新視窗
      const windowBlocks = Math.max(1, Math.round(CUT_WINDOW_SEC / blockSec))
      let cut = blocks.length
      let quietest = Infinity
      for (let i = blocks.length - 1; i >= Math.max(1, blocks.length - windowBlocks); i--) {
        if (blocks[i].vol < quietest) {
          quietest = blocks[i].vol
          cut = i + 1
        }
      }
      sendWindow(cut, false)
      windowIndex++
    } else {
      sendWindow(blocks.length, false)
    }
  }

  if (!hasVoice && !utteranceStarted && silenceSec >= props.settings.silenceTimeout) {
    vadStatus.value = '一段時間沒有聲音，自動結束'
    stopRecording()
    return
  }
  vadStatus.value = voiced ? '正在聆聽…' : (hasVoice ? '停頓中…' : '等待語音...')
}

// 送出視窗開頭的 n 個區塊。講話中（isFinal=false）且 n 是整個視窗時，區塊保留，
// 下次連同新錄的一起再送；切視窗或定稿時，送出的區塊就移除。
function sendWindow(n: number, isFinal: boolean) {
  const segment = blocks.slice(0, n)
  const voiceSec = segment.filter(b => b.voiced).length * blockSec

  if (voiceSec >= MIN_VOICE_SEC || utteranceStarted) {
    enqueueUpload(encodeWav(segment), utteranceId, windowIndex, isFinal)
    utteranceStarted = !isFinal
  }

  if (isFinal) {
    resetUtterance()
  } else if (n < blocks.length || blocks.length * blockSec >= WINDOW_MAX_SEC) {
    blocks.splice(0, n)
    hasVoice = blocks.some(b => b.voiced)
    sentBlocks = 0
  } else {
    sentBlocks = blocks.length
  }
}

function resetUtterance() {
  blocks = []
  sentBlocks = 0
  windowIndex = 0
  hasVoice = false
  utteranceId = newUtteranceId()
  utteranceStarted = false
}

// 前半段已送出，但後面沒有聲音了：送一個空段落讓後端定稿
function finishUtterance() {
  enqueueUpload(new Blob([], { type: 'audio/wav' }), utteranceId, windowIndex, true)
  resetUtterance()
}

function enqueueUpload(blob: Blob, uttId: string, window: number, isFinal: boolean) {
  const roomId = props.roomId
  const speakerName = props.speakerName || '未知用戶'
  uploadChain = uploadChain.then(async () => {
    try {
      const result = await speechApi.upload(roomId, blob, props.userLang, speakerName, { utteranceId: uttId, window, isFinal })
      emit('transcript', { text: result.transcript, confidence: result.confidence, lang: result.detected_lang })
    } catch (err) {
      console.error('❌ 分段上傳失敗:', err)
      emit('error', '分段音檔處理失敗')
    }
  })
}

async function stopRecording() {
  if (!isRecording.value) return
  if (hasVoice) {
    sendWindow(blocks.length, true)
  } else if (utteranceStarted) {
    finishUtterance()
  }
  isRecording.value = false
  teardownAudio()
  emit('recording-end')
}

function teardownAudio() {
  if (processor) {
    processor.onaudioprocess = null
    processor.disconnect()
  }
  sourceNode?.disconnect()
  analyser?.disconnect()
  audioContext?.close().catch(() => {})
  processor = null
  sourceNode = null
  analyser = null
  audioContext = null
  blocks = []
  hasVoice = false
  silenceSec = 0
  volumeLevel.value = 0
  isVoiceDetected.value = false
  recordingTime.value = 0
  vadStatus.value = '等待語音...'
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
    // 區間平均當作簡單的低通，避免降頻後出現雜音
    const start = Math.floor(i * ratio)
    const end = Math.min(total, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    const sample = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)))
    view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
  return new Blob([view], { type: 'audio/wav' })
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.smart-voice-recorder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
}

.smart-record-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 20px;
  padding: 1rem 2rem;
  cursor: pointer;
  font-size: 1rem;
  min-width: 200px;
  transition: all 0.3s ease;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
  position: relative;
  overflow: hidden;
}

.smart-record-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}

.smart-record-btn.recording {
  background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
  animation: recordingPulse 2s infinite;
}

.smart-record-btn.processing {
  background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
}

.smart-record-btn.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@keyframes recordingPulse {
  0%, 100% { box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3); }
  50% { box-shadow: 0 6px 25px rgba(231, 76, 60, 0.6); }
}

.btn-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.icon {
  font-size: 1.5rem;
}

.recording-animation {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.pulse {
  position: absolute;
  width: 30px;
  height: 30px;
  border: 2px solid rgba(255, 255, 255, 0.6);
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 1;
  }
  100% {
    transform: scale(2);
    opacity: 0;
  }
}

.text {
  text-align: center;
  line-height: 1.4;
}

.text small {
  font-size: 0.8rem;
  opacity: 0.9;
}

.smart-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  background: rgba(255, 255, 255, 0.95);
  padding: 1rem;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  min-width: 300px;
}

.volume-display {
  position: relative;
  width: 100%;
}

.volume-bars {
  display: flex;
  gap: 3px;
  align-items: end;
  justify-content: center;
  height: 40px;
}

.volume-bar {
  width: 6px;
  height: 8px;
  background: #e9ecef;
  border-radius: 3px;
  transition: all 0.1s;
}

.volume-bar.active {
  height: 20px;
}

.volume-bar.voice {
  background: linear-gradient(to top, #28a745, #20c997);
}

.volume-bar.silence {
  background: linear-gradient(to top, #6c757d, #adb5bd);
}

.threshold-line {
  position: absolute;
  top: 50%;
  width: 2px;
  height: 100%;
  background: #dc3545;
  transform: translateY(-50%);
  opacity: 0.7;
}

.threshold-line::before {
  content: '閾值';
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.7rem;
  color: #dc3545;
  white-space: nowrap;
}

.vad-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  text-align: center;
}

.vad-status {
  font-weight: 600;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  background: #f8f9fa;
  color: #6c757d;
  transition: all 0.3s;
}

.vad-status.active {
  background: #d4edda;
  color: #155724;
}

.silence-timer, .auto-stop-info {
  font-size: 0.8rem;
  color: #666;
}

.auto-stop-info {
  color: #e67e22;
  font-weight: 600;
}

.mode-selector {
  display: flex;
  gap: 0.5rem;
  background: #f8f9fa;
  padding: 0.25rem;
  border-radius: 20px;
}

.mode-btn {
  background: none;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 16px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.3s;
  color: #666;
}

.mode-btn.active {
  background: #667eea;
  color: white;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.error-message {
  background: #f8d7da;
  color: #721c24;
  padding: 0.75rem;
  border-radius: 8px;
  text-align: center;
  font-size: 0.9rem;
  max-width: 300px;
}

/* 響應式設計 */
@media (max-width: 768px) {
  .smart-voice-recorder {
    padding: 0.5rem;
  }
  
  .smart-record-btn {
    min-width: 180px;
    padding: 0.8rem 1.5rem;
  }
  
  .smart-indicator {
    min-width: 280px;
    padding: 0.8rem;
  }
  
  .volume-bars {
    height: 30px;
  }
  
  .volume-bar.active {
    height: 15px;
  }
}
</style>