<template>
  <div class="voice-recorder">
    <button
      @click="toggleRecording"
      :class="['record-btn', { 
        recording: isRecording, 
        processing: isProcessing,
        disabled: !isSupported 
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
            錄音中 {{ formatTime(recordingTime) }}
          </span>
          <span v-else>語音輸入</span>
        </div>
      </div>
    </button>
    
    <!-- 語言選擇 -->
    <select 
      v-model="selectedLang" 
      class="lang-select"
      :disabled="isRecording || isProcessing"
    >
      <option value="zh-TW">繁體中文</option>
      <option value="zh-CN">簡體中文</option>
      <option value="en-US">English</option>
      <option value="ja-JP">日本語</option>
      <option value="ko-KR">한국어</option>
      <option value="es-ES">Español</option>
      <option value="fr-FR">Français</option>
      <option value="de-DE">Deutsch</option>
      <option value="it-IT">Italiano</option>
      <option value="pt-PT">Português</option>
      <option value="ru-RU">Русский</option>
      <option value="ar-SA">العربية</option>
      <option value="hi-IN">हिन्दी</option>
      <option value="th-TH">ไทย</option>
      <option value="vi-VN">Tiếng Việt</option>
      <option value="my-MM">မြန်မာ (緬甸文)</option>
      <option value="id-ID">Bahasa Indonesia (印尼文)</option>
      <option value="ms-MY">Bahasa Melayu (馬來文)</option>
    </select>
    
    <!-- 錄音狀態指示器 -->
    <div v-if="isRecording" class="recording-indicator">
      <div class="volume-bars">
        <div 
          v-for="i in 5" 
          :key="i"
          class="volume-bar"
          :class="{ active: volumeLevel >= i }"
        ></div>
      </div>
    </div>
    
    <!-- 錯誤訊息 -->
    <div v-if="error" class="error-message">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { speechApi } from '@/api/speech'

interface Props {
  roomId: string
  disabled?: boolean
}

interface Emits {
  (e: 'transcript', result: { text: string; confidence: number; lang: string }): void
  (e: 'error', error: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 響應式狀態
const isSupported = ref(false)
const isRecording = ref(false)
const isProcessing = ref(false)
const selectedLang = ref('zh-TW')
const recordingTime = ref(0)
const volumeLevel = ref(0)
const error = ref('')

// 媒體相關
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
const stream = ref<MediaStream | null>(null)
const recordingTimer = ref<number | null>(null)
const volumeAnalyser = ref<AnalyserNode | null>(null)
const volumeAnimationFrame = ref<number | null>(null)

onMounted(() => {
  checkSupport()
})

onUnmounted(() => {
  cleanup()
})

function checkSupport() {
  isSupported.value = !!(
    navigator.mediaDevices &&
    navigator.mediaDevices.getUserMedia &&
    window.MediaRecorder
  )
}

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
    
    // 請求麥克風權限
    stream.value = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 48000
      }
    })
    
    // 設定音量分析
    setupVolumeAnalysis(stream.value)
    
    // 建立 MediaRecorder
    const mimeType = getSupportedMimeType()
    mediaRecorder.value = new MediaRecorder(stream.value, {
      mimeType: mimeType,
      audioBitsPerSecond: 128000
    })
    
    audioChunks.value = []
    
    mediaRecorder.value.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.value.push(event.data)
      }
    }
    
    mediaRecorder.value.onstop = async () => {
      await processRecording()
    }
    
    // 開始錄音
    mediaRecorder.value.start(100) // 每100ms收集一次數據
    isRecording.value = true
    recordingTime.value = 0
    
    // 開始計時
    recordingTimer.value = window.setInterval(() => {
      recordingTime.value++
    }, 1000)
    
    console.log('🎤 開始錄音')
    
  } catch (err) {
    console.error('錄音失敗:', err)
    error.value = '無法存取麥克風，請檢查權限設定'
    cleanup()
  }
}

async function stopRecording() {
  if (mediaRecorder.value && isRecording.value) {
    console.log('⏹️ 停止錄音')
    mediaRecorder.value.stop()
    isRecording.value = false
    
    if (recordingTimer.value) {
      clearInterval(recordingTimer.value)
      recordingTimer.value = null
    }
    
    stopVolumeAnalysis()
  }
}

async function processRecording() {
  if (audioChunks.value.length === 0) {
    error.value = '錄音資料為空'
    cleanup()
    return
  }
  
  try {
    isProcessing.value = true
    console.log('🔄 處理錄音資料...')
    
    // 合併音頻資料
    const mimeType = getSupportedMimeType()
    const audioBlob = new Blob(audioChunks.value, { type: mimeType })
    
    console.log(`📦 音頻資料大小: ${(audioBlob.size / 1024).toFixed(1)} KB`)
    
    // 上傳到後端進行 STT
    await uploadAudio(audioBlob)
    
  } catch (err) {
    console.error('處理錄音失敗:', err)
    error.value = '處理錄音失敗，請重試'
    emit('error', error.value)
  } finally {
    isProcessing.value = false
    cleanup()
  }
}

async function uploadAudio(audioBlob: Blob) {
  const formData = new FormData()
  formData.append('audio', audioBlob, `recording.${getFileExtension()}`)
  formData.append('room_id', props.roomId)
  formData.append('language_code', selectedLang.value)
  
  const token = localStorage.getItem('token')
  if (!token) {
    throw new Error('未登入')
  }
  
  const result = await speechApi.upload(props.roomId, audioBlob, props.userLang)
  console.log('✅ STT 成功:', result)
  
  // 發送轉錄結果
  emit('transcript', {
    text: result.transcript,
    confidence: result.confidence,
    lang: result.detected_lang
  })
}

function setupVolumeAnalysis(stream: MediaStream) {
  try {
    const audioContext = new AudioContext()
    const source = audioContext.createMediaStreamSource(stream)
    volumeAnalyser.value = audioContext.createAnalyser()
    
    volumeAnalyser.value.fftSize = 256
    volumeAnalyser.value.smoothingTimeConstant = 0.8
    
    source.connect(volumeAnalyser.value)
    
    // 開始音量分析動畫
    const analyzeVolume = () => {
      if (!volumeAnalyser.value || !isRecording.value) return
      
      const dataArray = new Uint8Array(volumeAnalyser.value.frequencyBinCount)
      volumeAnalyser.value.getByteFrequencyData(dataArray)
      
      // 計算平均音量
      const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length
      volumeLevel.value = Math.min(5, Math.floor((average / 255) * 10))
      
      volumeAnimationFrame.value = requestAnimationFrame(analyzeVolume)
    }
    
    analyzeVolume()
    
  } catch (err) {
    console.warn('無法設定音量分析:', err)
  }
}

function stopVolumeAnalysis() {
  if (volumeAnimationFrame.value) {
    cancelAnimationFrame(volumeAnimationFrame.value)
    volumeAnimationFrame.value = null
  }
  volumeLevel.value = 0
}

function getSupportedMimeType(): string {
  const types = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/wav'
  ]
  
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type
    }
  }
  
  return 'audio/webm' // 回退選項
}

function getFileExtension(): string {
  const mimeType = getSupportedMimeType()
  if (mimeType.includes('webm')) return 'webm'
  if (mimeType.includes('mp4')) return 'mp4'
  if (mimeType.includes('wav')) return 'wav'
  return 'webm'
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function cleanup() {
  if (stream.value) {
    stream.value.getTracks().forEach(track => track.stop())
    stream.value = null
  }
  
  if (recordingTimer.value) {
    clearInterval(recordingTimer.value)
    recordingTimer.value = null
  }
  
  stopVolumeAnalysis()
  audioChunks.value = []
  recordingTime.value = 0
}
</script>

<style scoped>
.voice-recorder {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.record-btn {
  background: #f8f9fa;
  border: 2px solid #dee2e6;
  border-radius: 2rem;
  padding: 0.75rem 1.5rem;
  cursor: pointer;
  transition: all 0.3s ease;
  min-width: 140px;
  position: relative;
  overflow: hidden;
}

.record-btn:hover:not(.disabled):not(:disabled) {
  background: #e9ecef;
  border-color: #adb5bd;
}

.record-btn.recording {
  background: #dc3545;
  border-color: #dc3545;
  color: white;
  animation: recordingPulse 2s infinite;
}

.record-btn.processing {
  background: #ffc107;
  border-color: #ffc107;
  color: #000;
}

.record-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: center;
}

.icon {
  font-size: 1.2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
}

.recording-animation {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pulse {
  position: absolute;
  width: 20px;
  height: 20px;
  border: 2px solid white;
  border-radius: 50%;
  animation: pulse 1s infinite;
}

.text {
  font-weight: 500;
  font-size: 0.9rem;
  white-space: nowrap;
}

.lang-select {
  padding: 0.5rem;
  border: 1px solid #dee2e6;
  border-radius: 0.5rem;
  background: white;
  font-size: 0.9rem;
  min-width: 120px;
}

.lang-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.recording-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.volume-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 20px;
}

.volume-bar {
  width: 3px;
  background: #dee2e6;
  border-radius: 1px;
  transition: all 0.1s ease;
}

.volume-bar:nth-child(1) { height: 6px; }
.volume-bar:nth-child(2) { height: 9px; }
.volume-bar:nth-child(3) { height: 12px; }
.volume-bar:nth-child(4) { height: 15px; }
.volume-bar:nth-child(5) { height: 18px; }

.volume-bar.active {
  background: #28a745;
}

.error-message {
  color: #dc3545;
  font-size: 0.8rem;
  margin-top: 0.25rem;
  max-width: 200px;
  line-height: 1.3;
}

@keyframes recordingPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 1;
  }
  100% {
    transform: scale(1.8);
    opacity: 0;
  }
}

/* 響應式設計 */
@media (max-width: 768px) {
  .voice-recorder {
    flex-direction: column;
    gap: 0.5rem;
    align-items: stretch;
  }
  
  .record-btn {
    min-width: auto;
    width: 100%;
  }
  
  .lang-select {
    width: 100%;
  }
}
</style>