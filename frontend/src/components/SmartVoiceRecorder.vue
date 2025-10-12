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
        <div class="threshold-line" :style="{ left: `${(settings.voiceThreshold / 50) * 100}%` }"></div>
      </div>
      
      <div class="vad-info">
        <div class="vad-status" :class="{ active: isVoiceDetected }">
          {{ isVoiceDetected ? '🎙️ 檢測到語音' : '🔇 靜音中' }}
        </div>
        <div class="silence-timer" v-if="!isVoiceDetected && silenceTimer > 0">
          靜音 {{ (settings.silenceTimeout - silenceTimer).toFixed(1) }}s
        </div>
        <div class="auto-stop-info" v-if="recordingTime >= settings.maxRecordingTime - 5">
          將在 {{ (settings.maxRecordingTime - recordingTime).toFixed(0) }}s 後自動結束
        </div>
      </div>
    </div>
    
    <!-- 錄音模式切換 -->
    <div class="mode-selector">
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
    </div>
    
    <!-- 錯誤訊息 -->
    <div v-if="error" class="error-message">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { speechApi } from '../api/speech'

interface SmartSettings {
  voiceThreshold: number
  silenceTimeout: number
  minRecordingTime: number
  maxRecordingTime: number
}

interface Props {
  roomId: string
  disabled?: boolean
  userLang?: string
  settings: SmartSettings
}

interface Emits {
  (e: 'transcript', result: { text: string; confidence: number; lang: string }): void
  (e: 'error', error: string): void
  (e: 'recording-start'): void
  (e: 'recording-end'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 響應式狀態
const isSupported = ref(false)
const isRecording = ref(false)
const isProcessing = ref(false)
const recordingTime = ref(0)
const volumeLevel = ref(0)
const error = ref('')
const recordingMode = ref<'smart' | 'manual'>('smart')

// 語音活動檢測 (VAD) 相關
const isVoiceDetected = ref(false)
const vadStatus = ref('等待語音...')
const silenceTimer = ref(0)
const voiceStartTime = ref(0)
const hasValidSpeech = ref(false)
const currentVolume = ref(0) // 當前音量百分比

// 自動分段錄音相關
const segmentTimer = ref(0)
const isSegmentMode = ref(false)
const segmentThreshold = 10 // 10%音量閾值用於分段
const minSegmentTime = 1.0 // 最少錄音1秒才能分段
const hasProcessedSegment = ref(false)

// 媒體相關
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
const stream = ref<MediaStream | null>(null)
const recordingTimer = ref<number | null>(null)
const volumeAnalyser = ref<AnalyserNode | null>(null)
const volumeAnimationFrame = ref<number | null>(null)
const vadTimer = ref<number | null>(null)

// 智能檢測參數
const vadSamples = ref<number[]>([])
const vadSampleSize = 5 // 取樣數量用於平滑處理

onMounted(() => {
  checkSupport()
})

onUnmounted(() => {
  fullCleanup()
})

// 監聽設定變化
watch(() => props.settings, () => {
  console.log('🔧 語音設定已更新:', props.settings)
}, { deep: true })

function checkSupport() {
  isSupported.value = !!(
    navigator.mediaDevices &&
    navigator.mediaDevices.getUserMedia &&
    window.MediaRecorder
  )
}

async function toggleRecording() {
  if (isRecording.value) {
    // 智能模式和手動模式都允許手動停止
    await stopRecording()
  } else {
    await startRecording()
  }
}

async function startRecording() {
  try {
    error.value = ''
    console.log('🎤 開始請求麥克風權限...')
    
    // 檢查瀏覽器是否支援
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('瀏覽器不支援麥克風功能')
    }
    
    // 請求麥克風權限
    stream.value = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 48000
      }
    })
    
    console.log('✅ 麥克風權限獲得成功')
    console.log('🎤 音頻軌道狀態:', stream.value.getAudioTracks().map(track => ({
      label: track.label,
      enabled: track.enabled,
      readyState: track.readyState,
      settings: track.getSettings()
    })))
    
    // 設定智能語音檢測
    setupSmartVAD(stream.value)
    
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
    mediaRecorder.value.start(100)
    isRecording.value = true
    recordingTime.value = 0
    silenceTimer.value = 0
    hasValidSpeech.value = false
    
    // 啟動音頻分析
    console.log('🚀 錄音已開始，現在啟動音頻分析...')
    startAudioAnalysis()
    
    // 開始計時
    recordingTimer.value = window.setInterval(() => {
      recordingTime.value += 0.1
      
      // 檢查最長錄音時間
      if (recordingTime.value >= props.settings.maxRecordingTime) {
        vadStatus.value = '達到最長錄音時間'
        stopRecording()
        return
      }
      
      // 智能模式下的自動停止邏輯
      if (recordingMode.value === 'smart') {
        handleSmartRecordingLogic().catch(error => {
          console.error('❌ 智能錄音邏輯錯誤:', error)
        })
      }
    }, 100)
    
    emit('recording-start')
    console.log('🎤 開始智能錄音')
    
  } catch (err) {
    console.error('錄音失敗:', err)
    error.value = '無法存取麥克風，請檢查權限設定'
    cleanup()
  }
}

async function handleSmartRecordingLogic() {
  // 在智能模式下才執行自動邏輯
  if (recordingMode.value !== 'smart') return
  
  // 使用實際音量數值進行判斷
  const currentVol = currentVolume.value
  const isLowVolume = currentVol <= segmentThreshold // 低於10%
  
  // 檢查自動分段邏輯（優先處理）
  if (recordingTime.value >= minSegmentTime && isLowVolume) {
    segmentTimer.value += 0.1
    
    // 如果已經錄音超過1秒，且音量持續低於10%，則進行分段
    if (segmentTimer.value >= 0.3 && hasValidSpeech.value) {
      vadStatus.value = '檢測到分段點，送出音檔...'
      console.log(`🎵 自動分段：錄音 ${recordingTime.value.toFixed(1)}s，音量 ${currentVol.toFixed(1)}% 低於 ${segmentThreshold}% 持續 ${segmentTimer.value.toFixed(1)}s`)
      await processCurrentSegment()
      return
    }
  } else if (!isLowVolume) {
    // 檢測到語音，重置分段計時器
    segmentTimer.value = 0
  }
  
  // 原有的結束邏輯 - 使用實際音量判斷
  if (isLowVolume) {
    silenceTimer.value += 0.1
    
    // 檢查是否達到靜音超時時間（完全結束錄音）
    if (silenceTimer.value >= props.settings.silenceTimeout) {
      // 如果有過有效語音，自動停止
      if (hasValidSpeech.value) {
        vadStatus.value = '靜音時間達到閾值，自動結束'
        console.log(`🔇 音量 ${currentVol.toFixed(1)}% 靜音 ${silenceTimer.value.toFixed(1)}s 達到閾值 ${props.settings.silenceTimeout}s，完全結束錄音`)
        stopRecording()
        return
      } else if (silenceTimer.value >= props.settings.silenceTimeout * 2) {
        // 如果一直沒有有效語音，延長一倍時間後停止
        vadStatus.value = '未檢測到有效語音，自動結束'
        console.log(`🔇 持續靜音 ${silenceTimer.value.toFixed(1)}s，未檢測到有效語音，自動結束`)
        stopRecording()
        return
      }
    }
    
    vadStatus.value = hasValidSpeech.value ? 
      `靜音中(${currentVol.toFixed(1)}%)，${Math.max(0, props.settings.silenceTimeout - silenceTimer.value).toFixed(1)}s後結束` :
      `等待語音輸入(${currentVol.toFixed(1)}%)... ${Math.max(0, props.settings.silenceTimeout * 2 - silenceTimer.value).toFixed(1)}s`
  } else {
    // 檢測到語音，重置靜音計時器
    silenceTimer.value = 0
    
    // 檢查是否達到最短錄音時間
    if (recordingTime.value >= props.settings.minRecordingTime) {
      hasValidSpeech.value = true
    }
    
    vadStatus.value = hasValidSpeech.value ? `正在錄製語音(${currentVol.toFixed(1)}%)...` : `檢測中(${currentVol.toFixed(1)}%)...`
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
    emit('recording-end')
  }
}

// 處理自動分段
async function processCurrentSegment() {
  if (!mediaRecorder.value || audioChunks.value.length === 0) {
    console.log('⚠️ 無音檔資料可分段')
    return
  }
  
  try {
    // 暫停當前錄音器（保持stream活躍）
    mediaRecorder.value.stop()
    
    // 等待ondataavailable事件完成
    await new Promise(resolve => {
      if (mediaRecorder.value) {
        mediaRecorder.value.onstop = resolve
      } else {
        resolve(undefined)
      }
    })
    
    // 處理當前音檔段落
    const segmentChunks = [...audioChunks.value]
    audioChunks.value = [] // 清空準備下一段
    
    if (segmentChunks.length > 0) {
      console.log('🎵 處理分段音檔...')
      const mimeType = getSupportedMimeType()
      const segmentBlob = new Blob(segmentChunks, { type: mimeType })
      
      // 異步上傳當前段落
      uploadSegmentAudio(segmentBlob)
    }
    
    // 重新開始錄音下一段
    await restartRecordingForNextSegment()
    
  } catch (error) {
    console.error('❌ 分段處理失敗:', error)
    // 如果分段失敗，繼續正常錄音
    await restartRecordingForNextSegment()
  }
}

// 重新開始錄音下一段
async function restartRecordingForNextSegment() {
  if (!stream.value) return
  
  try {
    // 建立新的 MediaRecorder
    const mimeType = getSupportedMimeType()
    mediaRecorder.value = new MediaRecorder(stream.value, {
      mimeType: mimeType,
      audioBitsPerSecond: 128000
    })
    
    mediaRecorder.value.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.value.push(event.data)
      }
    }
    
    mediaRecorder.value.onstop = async () => {
      await processRecording()
    }
    
    // 重新開始錄音
    mediaRecorder.value.start(100)
    
    // 重置分段相關狀態
    segmentTimer.value = 0
    hasValidSpeech.value = false
    
    console.log('🎤 開始錄音新段落')
    
  } catch (error) {
    console.error('❌ 重新開始錄音失敗:', error)
    await stopRecording()
  }
}

// 異步上傳分段音檔
async function uploadSegmentAudio(audioBlob: Blob) {
  try {
    console.log(`📤 上傳分段音檔，大小: ${(audioBlob.size / 1024).toFixed(1)} KB`)
    
    const result = await speechApi.upload(props.roomId, audioBlob, props.userLang)
    console.log('✅ 分段音檔STT成功:', result)
    
    emit('transcript', {
      text: result.transcript,
      confidence: result.confidence,
      lang: result.detected_lang
    })
    
  } catch (error) {
    console.error('❌ 分段音檔上傳失敗:', error)
    emit('error', '分段音檔處理失敗')
  }
}

// 音頻分析相關變量
let debugCounter = 0

function setupSmartVAD(stream: MediaStream) {
  try {
    console.log('🔧 開始設定語音檢測...')
    
    const audioContext = new AudioContext()
    console.log('🎵 AudioContext 狀態:', audioContext.state)
    
    // 如果AudioContext被暫停，嘗試恢復
    if (audioContext.state === 'suspended') {
      audioContext.resume().then(() => {
        console.log('🎵 AudioContext 已恢復')
      })
    }
    
    const source = audioContext.createMediaStreamSource(stream)
    volumeAnalyser.value = audioContext.createAnalyser()
    
    // 調整設定以獲得更好的語音檢測
    volumeAnalyser.value.fftSize = 256
    volumeAnalyser.value.smoothingTimeConstant = 0.8
    
    source.connect(volumeAnalyser.value)
    console.log('🔗 音頻源已連接到分析器')
    
    console.log('✅ 語音檢測設定完成，等待錄音開始後啟動分析')
    
  } catch (err) {
    console.error('❌ 無法設定語音檢測:', err)
    error.value = '語音檢測設定失敗：' + err.message
  }
}

function startAudioAnalysis() {
  if (!volumeAnalyser.value) {
    console.error('❌ 無法啟動音頻分析：分析器未初始化')
    return
  }
  
  debugCounter = 0 // 重置計數器
  console.log('🎯 啟動音頻分析循環...')
  
  const analyzeAudio = () => {
    // 添加進入函數的LOG
    console.log(`🎯 analyzeAudio 函數執行中... 錄音狀態: ${isRecording.value}, 分析器狀態: ${!!volumeAnalyser.value}`)
    
    if (!volumeAnalyser.value || !isRecording.value) {
      console.log(`⚠️ analyzeAudio 提前返回: 分析器=${!!volumeAnalyser.value}, 錄音中=${isRecording.value}`)
      return
    }
    
    const dataArray = new Uint8Array(volumeAnalyser.value.frequencyBinCount)
    volumeAnalyser.value.getByteFrequencyData(dataArray)
    
    // 使用原本有效的音量計算方式
    const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length
    const normalizedVolume = Math.min(100, (average / 255) * 100)
    
    // 調試：每50幀輸出一次音量信息
    debugCounter++
    if (debugCounter % 50 === 0) {
      const threshold = props.settings.voiceThreshold
      console.log(`🔊 原始音量: ${average.toFixed(1)}, 標準化音量: ${normalizedVolume.toFixed(1)}%, 閾值: ${threshold}%, 數據範圍: ${Math.min(...dataArray)}-${Math.max(...dataArray)}`)
    }
    
    // 每5幀輸出基本狀態確認analyzeAudio在運行
    if (debugCounter % 5 === 0) {
      console.log(`🔄 analyzeAudio 第${debugCounter}幀: 平均音量=${average.toFixed(1)}, 標準化=${normalizedVolume.toFixed(1)}%`)
    }
    
    // 平滑處理 - 添加詳細LOG
    vadSamples.value.push(normalizedVolume)
    if (vadSamples.value.length > vadSampleSize) {
      vadSamples.value.shift()
    }
    
    const smoothedVolume = vadSamples.value.reduce((sum, val) => sum + val, 0) / vadSamples.value.length
    
    // 詳細調試LOG - 每20幀輸出平滑處理詳情
    if (debugCounter % 20 === 0) {
      console.log(`🔍 平滑處理詳情:`)
      console.log(`  - 原始音量: ${normalizedVolume.toFixed(2)}%`)
      console.log(`  - 樣本數組: [${vadSamples.value.map(v => v.toFixed(1)).join(', ')}]`)
      console.log(`  - 樣本數量: ${vadSamples.value.length}/${vadSampleSize}`)
      console.log(`  - 樣本總和: ${vadSamples.value.reduce((sum, val) => sum + val, 0).toFixed(2)}`)
      console.log(`  - 平滑後音量: ${smoothedVolume.toFixed(2)}%`)
      console.log(`  - 音量條等級: ${volumeLevel.value}/10`)
    }
    volumeLevel.value = Math.min(10, Math.floor(smoothedVolume / 10))
    
    // 更新當前音量
    currentVolume.value = smoothedVolume
    
    // 語音活動檢測 - 使用設定的閾值
    const threshold = props.settings.voiceThreshold
    const wasVoiceDetected = isVoiceDetected.value
    isVoiceDetected.value = smoothedVolume > threshold
    
    // 調試：語音檢測狀態改變時輸出
    if (wasVoiceDetected !== isVoiceDetected.value) {
      console.log(`🎙️ 語音檢測狀態變化: ${isVoiceDetected.value ? '檢測到語音' : '靜音'} (平滑音量: ${smoothedVolume.toFixed(1)}%, 設定閾值: ${threshold}%)`)
    }
    
    // 額外調試：每100幀輸出當前檢測狀態和分段狀態
    if (debugCounter % 100 === 0) {
      const segmentInfo = recordingTime.value >= minSegmentTime ? 
        `分段計時: ${segmentTimer.value.toFixed(1)}s` : 
        '未達分段時間'
      console.log(`📊 當前狀態: 音量=${smoothedVolume.toFixed(1)}%, 閾值=${threshold}%, 檢測=${isVoiceDetected.value ? '有語音' : '靜音'}, 錄音時間=${recordingTime.value.toFixed(1)}s, ${segmentInfo}`)
    }
    
    volumeAnimationFrame.value = requestAnimationFrame(analyzeAudio)
    
    // 確認下一幀已安排
    if (debugCounter % 10 === 0) {
      console.log(`🔄 已安排下一幀分析: ${volumeAnimationFrame.value}`)
    }
  }
  
  // 開始分析
  analyzeAudio()
}

function stopVolumeAnalysis() {
  if (volumeAnimationFrame.value) {
    cancelAnimationFrame(volumeAnimationFrame.value)
    volumeAnimationFrame.value = null
  }
  volumeLevel.value = 0
  isVoiceDetected.value = false
  vadSamples.value = []
  volumeAnalyser.value = null
}

async function processRecording() {
  if (audioChunks.value.length === 0) {
    error.value = '錄音資料為空'
    cleanup()
    return
  }
  
  // 檢查最短錄音時間 - 但只在智能模式下檢查，手動模式不限制
  if (recordingMode.value === 'smart' && recordingTime.value < props.settings.minRecordingTime) {
    console.log(`⚠️ 智能模式錄音時間過短 (${recordingTime.value.toFixed(1)}s < ${props.settings.minRecordingTime}s)，忽略此次錄音`)
    cleanup()
    return
  }
  
  console.log(`✅ 錄音時間符合要求 (${recordingTime.value.toFixed(1)}s)，開始處理音檔`)
  
  try {
    isProcessing.value = true
    console.log('🔄 處理錄音資料...')
    
    const mimeType = getSupportedMimeType()
    const audioBlob = new Blob(audioChunks.value, { type: mimeType })
    
    console.log(`📦 音頻資料大小: ${(audioBlob.size / 1024).toFixed(1)} KB，時長: ${recordingTime.value.toFixed(1)}s`)
    
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
  const token = localStorage.getItem('token')
  if (!token) {
    throw new Error('未登入')
  }
  
  const result = await speechApi.upload(props.roomId, audioBlob, props.userLang)
  console.log('✅ STT 成功:', result)
  
  emit('transcript', {
    text: result.transcript,
    confidence: result.confidence,
    lang: result.detected_lang
  })
}

function getSupportedMimeType(): string {
  const types = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
    'audio/wav'
  ]
  
  return types.find(type => MediaRecorder.isTypeSupported(type)) || 'audio/webm'
}

function getFileExtension(): string {
  const mimeType = getSupportedMimeType()
  if (mimeType.includes('webm')) return 'webm'
  if (mimeType.includes('mp4')) return 'mp4'
  if (mimeType.includes('ogg')) return 'ogg'
  if (mimeType.includes('wav')) return 'wav'
  return 'webm'
}

function cleanup() {
  // 關鍵修復：不要停止 stream，保持麥克風權限活躍
  // 只清理錄音相關的資源
  
  stopVolumeAnalysis()
  
  if (recordingTimer.value) {
    clearInterval(recordingTimer.value)
    recordingTimer.value = null
  }
  
  if (vadTimer.value) {
    clearInterval(vadTimer.value)
    vadTimer.value = null
  }
  
  audioChunks.value = []
  recordingTime.value = 0
  silenceTimer.value = 0
  hasValidSpeech.value = false
  vadStatus.value = '等待語音...'
  
  // 重置分段相關狀態
  segmentTimer.value = 0
  isSegmentMode.value = false
  hasProcessedSegment.value = false
}

// 完全清理資源（僅在組件卸載時調用）
function fullCleanup() {
  if (stream.value) {
    stream.value.getTracks().forEach(track => track.stop())
    stream.value = null
  }
  cleanup()
  if (mediaRecorder.value) {
    mediaRecorder.value = null
  }
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