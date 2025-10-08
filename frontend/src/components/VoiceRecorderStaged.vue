<template>
  <div class="voice-recorder-staged">
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
          <span v-else-if="isProcessing">辨識中...</span>
          <span v-else-if="isRecording">
            錄音中 {{ formatTime(recordingTime) }}
          </span>
          <span v-else>分段語音</span>
        </div>
      </div>
    </button>
    
    <!-- STT 結果確認對話框 -->
    <div v-if="showTranscriptDialog" class="transcript-dialog-overlay" @click="closeDialog">
      <div class="transcript-dialog" @click.stop>
        <div class="dialog-header">
          <h3>語音辨識結果</h3>
          <button @click="closeDialog" class="close-btn">✕</button>
        </div>
        
        <div class="dialog-content">
          <div class="confidence-info">
            <span class="confidence-label">辨識信心度:</span>
            <span :class="['confidence-value', getConfidenceClass(transcriptResult.confidence)]">
              {{ Math.round(transcriptResult.confidence * 100) }}%
            </span>
            <span class="detected-lang">{{ getLanguageName(transcriptResult.detected_lang) }}</span>
          </div>
          
          <div class="transcript-edit">
            <label>辨識文字 (可修正):</label>
            <textarea 
              v-model="editableTranscript"
              class="transcript-textarea"
              rows="3"
              placeholder="請確認或修正辨識文字..."
            ></textarea>
          </div>
          
          <div class="action-buttons">
            <button @click="cancelTranscript" class="cancel-btn">
              取消
            </button>
            <button @click="confirmAndTranslate" :disabled="!editableTranscript.trim()" class="confirm-btn">
              確認並翻譯
            </button>
          </div>
        </div>
      </div>
    </div>
    
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
import { speechStagedApi } from '@/api/speech'

interface Props {
  roomId: string
  disabled?: boolean
}

interface Emits {
  (e: 'stt-preview', result: { transcript: string; confidence: number; detectedLang: string }): void
  (e: 'translation-start', data: { messageId: string; finalText: string; sourceLang: string }): void
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

// STT 結果對話框
const showTranscriptDialog = ref(false)
const transcriptResult = ref({
  transcript_id: '',
  transcript: '',
  confidence: 0,
  detected_lang: ''
})
const editableTranscript = ref('')

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
      await processSTT()
    }
    
    // 開始錄音
    mediaRecorder.value.start(100)
    isRecording.value = true
    recordingTime.value = 0
    
    // 開始計時
    recordingTimer.value = window.setInterval(() => {
      recordingTime.value++
    }, 1000)
    
    console.log('🎤 開始分段錄音')
    
  } catch (err) {
    console.error('錄音失敗:', err)
    error.value = '無法存取麥克風，請檢查權限設定'
    cleanup()
  }
}

async function stopRecording() {
  if (mediaRecorder.value && isRecording.value) {
    console.log('⏹️ 停止錄音，準備進行語音辨識')
    mediaRecorder.value.stop()
    isRecording.value = false
    
    if (recordingTimer.value) {
      clearInterval(recordingTimer.value)
      recordingTimer.value = null
    }
    
    stopVolumeAnalysis()
  }
}

async function processSTT() {
  if (audioChunks.value.length === 0) {
    error.value = '錄音資料為空'
    cleanup()
    return
  }
  
  try {
    isProcessing.value = true
    console.log('🔄 步驟 1: 語音辨識...')
    
    // 合併音頻資料
    const mimeType = getSupportedMimeType()
    const audioBlob = new Blob(audioChunks.value, { type: mimeType })
    
    console.log(`📦 音頻資料大小: ${(audioBlob.size / 1024).toFixed(1)} KB`)
    
    // 上傳到後端進行 STT（步驟 1）
    const sttResult = await uploadForSTT(audioBlob)
    
    // 顯示 STT 結果確認對話框
    showTranscriptConfirmation(sttResult)
    
  } catch (err) {
    console.error('語音辨識失敗:', err)
    error.value = '語音辨識失敗，請重試'
    emit('error', error.value)
  } finally {
    isProcessing.value = false
    cleanup()
  }
}

async function uploadForSTT(audioBlob: Blob) {
  const formData = new FormData()
  formData.append('audio', audioBlob, `recording.${getFileExtension()}`)
  formData.append('room_id', props.roomId)
  formData.append('language_code', selectedLang.value)
  
  const token = localStorage.getItem('token')
  if (!token) {
    throw new Error('未登入')
  }
  
  const result = await speechStagedApi.sttOnly(props.roomId, audioBlob, selectedLang.value)
  console.log('✅ 步驟 1 完成 - 語音辨識:', result)
  
  return result
}

function showTranscriptConfirmation(sttResult: any) {
  transcriptResult.value = sttResult
  editableTranscript.value = sttResult.transcript
  showTranscriptDialog.value = true
  
  // 發送 STT 預覽事件
  emit('stt-preview', {
    transcript: sttResult.transcript,
    confidence: sttResult.confidence,
    detectedLang: sttResult.detected_lang
  })
}

async function confirmAndTranslate() {
  if (!editableTranscript.value.trim()) return
  
  try {
    isProcessing.value = true
    console.log('🔄 步驟 2: 文字翻譯...')
    
    const result = await speechStagedApi.translateStt(
      transcriptResult.value.transcript_id,
      props.roomId
    )
    console.log('✅ 步驟 2 完成 - 翻譯處理:', result)
    
    // 發送翻譯開始事件
    emit('translation-start', {
      messageId: result.message_id,
      finalText: result.final_text,
      sourceLang: result.source_lang
    })
    
    closeDialog()
    
  } catch (err) {
    console.error('翻譯失敗:', err)
    error.value = '翻譯失敗，請重試'
    emit('error', error.value)
  } finally {
    isProcessing.value = false
  }
}

async function cancelTranscript() {
  try {
    if (transcriptResult.value.transcript_id) {
      await speechStagedApi.deleteTranscript(transcriptResult.value.transcript_id)
    }
  } catch (err) {
    console.warn('取消 STT 結果失敗:', err)
  }
  
  closeDialog()
}

function closeDialog() {
  showTranscriptDialog.value = false
  transcriptResult.value = {
    transcript_id: '',
    transcript: '',
    confidence: 0,
    detected_lang: ''
  }
  editableTranscript.value = ''
}

function getConfidenceClass(confidence: number): string {
  if (confidence >= 0.8) return 'high'
  if (confidence >= 0.6) return 'medium'
  return 'low'
}

function getLanguageName(langCode: string): string {
  const names: Record<string, string> = {
    'zh-TW': '繁體中文',
    'zh-CN': '簡體中文',
    'en': 'English',
    'ja': '日本語',
    'ko': '한국어'
  }
  return names[langCode] || langCode
}

// 重用原有的工具函數
function setupVolumeAnalysis(stream: MediaStream) {
  try {
    const audioContext = new AudioContext()
    const source = audioContext.createMediaStreamSource(stream)
    volumeAnalyser.value = audioContext.createAnalyser()
    
    volumeAnalyser.value.fftSize = 256
    volumeAnalyser.value.smoothingTimeConstant = 0.8
    
    source.connect(volumeAnalyser.value)
    
    const analyzeVolume = () => {
      if (!volumeAnalyser.value || !isRecording.value) return
      
      const dataArray = new Uint8Array(volumeAnalyser.value.frequencyBinCount)
      volumeAnalyser.value.getByteFrequencyData(dataArray)
      
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
  
  return 'audio/webm'
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
.voice-recorder-staged {
  display: flex;
  align-items: center;
  gap: 1rem;
  position: relative;
}

.record-btn {
  background: #f8f9fa;
  border: 2px solid #dee2e6;
  border-radius: 2rem;
  padding: 0.75rem 1.5rem;
  cursor: pointer;
  transition: all 0.3s ease;
  min-width: 120px;
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

/* STT 結果對話框 */
.transcript-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.transcript-dialog {
  background: white;
  border-radius: 1rem;
  padding: 2rem;
  max-width: 500px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.dialog-header h3 {
  margin: 0;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #666;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.confidence-info {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  padding: 1rem;
  background: #f8f9fa;
  border-radius: 0.5rem;
}

.confidence-label {
  font-weight: 500;
}

.confidence-value {
  font-weight: bold;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.confidence-value.high {
  background: #d4edda;
  color: #155724;
}

.confidence-value.medium {
  background: #fff3cd;
  color: #856404;
}

.confidence-value.low {
  background: #f8d7da;
  color: #721c24;
}

.detected-lang {
  background: #e9ecef;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.9rem;
}

.transcript-edit {
  margin-bottom: 1.5rem;
}

.transcript-edit label {
  display: block;
  font-weight: 500;
  margin-bottom: 0.5rem;
  color: #333;
}

.transcript-textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #ddd;
  border-radius: 0.5rem;
  font-size: 1rem;
  line-height: 1.5;
  resize: vertical;
  font-family: inherit;
}

.transcript-textarea:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.action-buttons {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
}

.cancel-btn {
  padding: 0.75rem 1.5rem;
  background: #6c757d;
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
}

.confirm-btn {
  padding: 0.75rem 1.5rem;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
}

.confirm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 其他樣式重用原有組件 */
.lang-select {
  padding: 0.5rem;
  border: 1px solid #dee2e6;
  border-radius: 0.5rem;
  background: white;
  font-size: 0.9rem;
  min-width: 120px;
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
</style>