<template>
  <div v-if="show" class="modal-overlay" @click="handleOverlayClick">
    <div class="modal-container" @click.stop>
      <div class="modal-header">
        <h2>🔧 個人設定</h2>
        <button @click="closeModal" class="close-btn">✕</button>
      </div>
      
      <div class="modal-body">
        <form @submit.prevent="saveSettings">
          
          <!-- 基本設定 -->
          <section class="settings-section">
            <h3>👤 基本設定</h3>
            
            <div class="form-group">
              <label class="form-label">顯示名稱</label>
              <input
                v-model="localSettings.displayName"
                type="text"
                class="form-input"
                placeholder="請輸入您的名稱"
                required
              />
            </div>
            
            <div class="form-group">
              <label class="form-label">我要看到的字幕語言</label>
              <select v-model="localSettings.inputLang" class="form-select" required>
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
                <option value="my">မြန်မာ (緬甸文)</option>
                <option value="id">Bahasa Indonesia (印尼文)</option>
                <option value="ms">Bahasa Melayu (馬來文)</option>
                <option value="yue">廣東話</option>
              </select>
              <p class="form-help">別人說話時，您看到的翻譯語言</p>
            </div>

            <div class="form-group">
              <label class="form-label">大白板語言（我說話時）</label>
              <select v-model="localSettings.outputLang" class="form-select" required>
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
                <option value="my">မြန်မာ (緬甸文)</option>
                <option value="id">Bahasa Indonesia (印尼文)</option>
                <option value="ms">Bahasa Melayu (馬來文)</option>
                <option value="yue">廣東話</option>
              </select>
              <p class="form-help">您說話時，大白板上顯示的翻譯語言</p>
            </div>
          </section>

          <!-- 進階語音設定 -->
          <section class="settings-section">
            <h3>🎤 進階語音設定</h3>
            
            <div class="form-group">
              <label class="form-label">
                語音檢測閾值 
                <span class="threshold-value">{{ localSettings.segmentThreshold }}%</span>
              </label>
              <input
                v-model.number="localSettings.segmentThreshold"
                type="range"
                min="1"
                max="30"
                class="form-range"
              />
              <p class="form-help">低於此音量視為靜音，用於自動分段和語音檢測</p>
            </div>
            
            <div class="form-group">
              <label class="form-label">
                靜音結束時間 
                <span class="threshold-value">{{ localSettings.silenceTimeout }}秒</span>
              </label>
              <input
                v-model.number="localSettings.silenceTimeout"
                type="range"
                min="1"
                max="10"
                class="form-range"
              />
              <p class="form-help">靜音超過此時間自動結束錄音</p>
            </div>
            
            <div class="form-group">
              <label class="form-label">
                最短分段時間 
                <span class="threshold-value">{{ localSettings.minSegmentTime }}秒</span>
              </label>
              <input
                v-model.number="localSettings.minSegmentTime"
                type="range"
                min="0.5"
                max="3"
                step="0.5"
                class="form-range"
              />
              <p class="form-help">錄音至少需要此時間才能進行自動分段</p>
            </div>
            
            <div class="form-group">
              <label class="form-label">
                分段延遲時間 
                <span class="threshold-value">{{ localSettings.segmentDelay }}秒</span>
              </label>
              <input
                v-model.number="localSettings.segmentDelay"
                type="range"
                min="0.5"
                max="3"
                step="0.5"
                class="form-range"
              />
              <p class="form-help">音量低於閾值後持續此時間才會送出音檔</p>
            </div>
            
            <div class="form-group">
              <label class="form-label">
                最長連續錄音時間 
                <span class="threshold-value">{{ localSettings.maxRecordingTime }}秒</span>
              </label>
              <input
                v-model.number="localSettings.maxRecordingTime"
                type="range"
                min="5"
                max="60"
                class="form-range"
              />
              <p class="form-help">連續錄音超過此時間自動強制分段</p>
            </div>
          </section>
          
          <!-- 測試區域 -->
          <section class="settings-section">
            <h3>🧪 語音測試</h3>
            <div class="test-section">
              <button 
                type="button" 
                @click="testVoiceDetection" 
                :disabled="isTesting"
                class="test-btn"
              >
                {{ isTesting ? '測試中...' : '🎤 測試語音檢測' }}
              </button>
              <div v-if="isTesting" class="test-indicator">
                <div class="volume-bars">
                  <div 
                    v-for="i in 10" 
                    :key="i"
                    class="volume-bar"
                    :class="{ active: testVolumeLevel >= i }"
                  ></div>
                </div>
                <p class="test-status">{{ testStatus }}</p>
              </div>
            </div>
          </section>
        </form>
      </div>
      
      <div class="modal-footer">
        <button type="button" @click="resetToDefaults" class="btn-secondary">
          重置預設值
        </button>
        <button type="button" @click="closeModal" class="btn-secondary">
          取消
        </button>
        <button @click="saveSettings" :disabled="saving" class="btn-primary">
          {{ saving ? '儲存中...' : '儲存設定' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted } from 'vue'

interface AdvancedSettings {
  displayName: string
  inputLang: string
  outputLang: string
  segmentThreshold: number    // 語音檢測閾值（合併聲音檢測閾值和自動分段閾值）
  silenceTimeout: number      // 靜音超時時間（多久沒聲音後結束錄音）
  minSegmentTime: number      // 最短分段時間（合併最短錄音時間和最短分段時間）
  segmentDelay: number        // 分段延遲時間（低於閾值後持續多久才送出）
  maxRecordingTime: number    // 最長連續錄音時間
}

interface Props {
  show: boolean
  initialSettings?: Partial<AdvancedSettings>
  isFirstTime?: boolean
}

interface Emits {
  (e: 'close'): void
  (e: 'save', settings: AdvancedSettings): void
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  isFirstTime: false
})

const emit = defineEmits<Emits>()

// 預設設定值
const defaultSettings: AdvancedSettings = {
  displayName: '',
  inputLang: 'zh-TW',
  outputLang: 'zh-TW',
  segmentThreshold: 10,     // 10%語音檢測閾值
  silenceTimeout: 5,        // 5秒靜音超時
  minSegmentTime: 1.0,      // 1秒最短分段時間
  segmentDelay: 1.0,        // 1秒分段延遲
  maxRecordingTime: 30      // 30秒最長連續錄音
}

// 本地設定狀態
const localSettings = reactive<AdvancedSettings>({ ...defaultSettings })
const saving = ref(false)

// 語音測試相關
const isTesting = ref(false)
const testVolumeLevel = ref(0)
const testStatus = ref('')
const testStream = ref<MediaStream | null>(null)
const testAnalyser = ref<AnalyserNode | null>(null)
const testAnimationFrame = ref<number | null>(null)

// 監聽props變化，更新本地設定
watch(() => props.initialSettings, (newSettings) => {
  if (newSettings) {
    Object.assign(localSettings, { ...defaultSettings, ...newSettings })
  }
}, { immediate: true })

onMounted(() => {
  // 如果是首次進入，生成隨機用戶名
  if (props.isFirstTime && !localSettings.displayName) {
    localSettings.displayName = `用戶_${Math.random().toString(36).substr(2, 6)}`
  }
})

onUnmounted(() => {
  stopVoiceTest()
})

function handleOverlayClick() {
  // 首次設定時不允許點擊背景關閉
  if (!props.isFirstTime) {
    closeModal()
  }
}

function closeModal() {
  if (props.isFirstTime && !isSettingsComplete()) {
    alert('請完成基本設定後再繼續')
    return
  }
  emit('close')
}

function isSettingsComplete(): boolean {
  return !!(localSettings.displayName.trim() && localSettings.inputLang && localSettings.outputLang)
}

async function saveSettings() {
  if (!isSettingsComplete()) {
    alert('請填寫完整的基本設定')
    return
  }

  try {
    saving.value = true
    
    // 模擬保存延遲
    await new Promise(resolve => setTimeout(resolve, 500))
    
    emit('save', { ...localSettings })
    
    if (!props.isFirstTime) {
      emit('close')
    }
  } catch (error) {
    console.error('儲存設定失敗:', error)
    alert('儲存設定失敗，請重試')
  } finally {
    saving.value = false
  }
}

function resetToDefaults() {
  if (confirm('確定要重置為預設值嗎？')) {
    Object.assign(localSettings, defaultSettings)
    if (props.isFirstTime) {
      localSettings.displayName = `用戶_${Math.random().toString(36).substr(2, 6)}`
    }
  }
}

async function testVoiceDetection() {
  if (isTesting.value) {
    stopVoiceTest()
    return
  }

  try {
    isTesting.value = true
    testStatus.value = '正在啟動麥克風...'
    console.log('🧪 開始語音測試...')
    
    // 檢查瀏覽器支援
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('瀏覽器不支援麥克風功能')
    }
    
    testStream.value = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    })
    
    console.log('✅ 測試麥克風權限獲得成功')
    console.log('🎤 測試音頻軌道:', testStream.value.getAudioTracks().map(track => ({
      label: track.label,
      enabled: track.enabled,
      readyState: track.readyState
    })))
    
    setupVoiceTest(testStream.value)
    testStatus.value = '語音檢測中，請說話測試...'
    
    // 10秒後自動停止測試
    setTimeout(() => {
      if (isTesting.value) {
        stopVoiceTest()
      }
    }, 10000)
    
  } catch (error) {
    console.error('❌ 語音測試失敗:', error)
    testStatus.value = `無法存取麥克風: ${error.message}`
    isTesting.value = false
  }
}

function setupVoiceTest(stream: MediaStream) {
  try {
    console.log('🔧 設定語音測試分析器...')
    
    const audioContext = new AudioContext()
    console.log('🎵 測試 AudioContext 狀態:', audioContext.state)
    
    // 如果AudioContext被暫停，嘗試恢復
    if (audioContext.state === 'suspended') {
      audioContext.resume().then(() => {
        console.log('🎵 測試 AudioContext 已恢復')
      })
    }
    
    const source = audioContext.createMediaStreamSource(stream)
    testAnalyser.value = audioContext.createAnalyser()
    
    testAnalyser.value.fftSize = 256
    testAnalyser.value.smoothingTimeConstant = 0.8
    
    source.connect(testAnalyser.value)
    console.log('🔗 測試音頻源已連接')
    
    let testDebugCounter = 0
    
    const analyzeVolume = () => {
      if (!testAnalyser.value || !isTesting.value) return
      
      const dataArray = new Uint8Array(testAnalyser.value.frequencyBinCount)
      testAnalyser.value.getByteFrequencyData(dataArray)
      
      const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length
      const normalizedVolume = Math.min(100, (average / 255) * 100)
      
      // 調試：每30幀輸出一次
      testDebugCounter++
      if (testDebugCounter % 30 === 0) {
        console.log(`🧪 測試音量: ${average.toFixed(1)} -> ${normalizedVolume.toFixed(1)}%, 範圍: ${Math.min(...dataArray)}-${Math.max(...dataArray)}`)
      }
      
      testVolumeLevel.value = Math.floor(normalizedVolume / 10)
      
      // 根據閾值更新狀態
      if (normalizedVolume > localSettings.segmentThreshold) {
        testStatus.value = `檢測到語音 (${normalizedVolume.toFixed(1)}%)`
      } else {
        testStatus.value = `靜音中 (${normalizedVolume.toFixed(1)}%)`
      }
      
      testAnimationFrame.value = requestAnimationFrame(analyzeVolume)
    }
    
    analyzeVolume()
    console.log('✅ 語音測試分析器設定完成')
    
  } catch (error) {
    console.error('❌ 設定語音分析失敗:', error)
    testStatus.value = '測試設定失敗: ' + error.message
  }
}

function stopVoiceTest() {
  isTesting.value = false
  testStatus.value = ''
  testVolumeLevel.value = 0
  
  if (testAnimationFrame.value) {
    cancelAnimationFrame(testAnimationFrame.value)
    testAnimationFrame.value = null
  }
  
  if (testStream.value) {
    testStream.value.getTracks().forEach(track => track.stop())
    testStream.value = null
  }
  
  testAnalyser.value = null
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal-container {
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  max-width: 600px;
  width: 90vw;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.modal-header h2 {
  margin: 0;
  font-size: 1.4rem;
}

.close-btn {
  background: none;
  border: none;
  color: white;
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.3s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.modal-body {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
}

.settings-section {
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #f0f0f0;
}

.settings-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.settings-section h3 {
  margin: 0 0 1.5rem 0;
  color: #333;
  font-size: 1.1rem;
  font-weight: 600;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #333;
  font-size: 0.95rem;
}

.threshold-value {
  color: #667eea;
  font-weight: 700;
  font-size: 0.9rem;
}

.form-input, .form-select {
  width: 100%;
  padding: 0.75rem;
  border: 2px solid #e9ecef;
  border-radius: 8px;
  font-size: 1rem;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.form-input:focus, .form-select:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-range {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e9ecef;
  outline: none;
  -webkit-appearance: none;
}

.form-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #667eea;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.form-range::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #667eea;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.form-help {
  margin-top: 0.5rem;
  font-size: 0.85rem;
  color: #666;
  line-height: 1.4;
}

.test-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: center;
}

.test-btn {
  background: #28a745;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.test-btn:hover:not(:disabled) {
  background: #218838;
}

.test-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.test-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.volume-bars {
  display: flex;
  gap: 3px;
  align-items: end;
}

.volume-bar {
  width: 4px;
  height: 8px;
  background: #e9ecef;
  border-radius: 2px;
  transition: all 0.1s;
}

.volume-bar.active {
  background: #28a745;
  height: 16px;
}

.test-status {
  margin: 0;
  font-size: 0.9rem;
  color: #666;
  text-align: center;
}

.modal-footer {
  display: flex;
  gap: 1rem;
  padding: 1.5rem 2rem;
  border-top: 1px solid #e9ecef;
  background: #f8f9fa;
  justify-content: flex-end;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.btn-secondary:hover {
  background: #5a6268;
}

.btn-primary {
  background: #667eea;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.btn-primary:hover:not(:disabled) {
  background: #5a6fd8;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 響應式設計 */
@media (max-width: 768px) {
  .modal-container {
    width: 95vw;
    max-height: 95vh;
  }
  
  .modal-header, .modal-body, .modal-footer {
    padding: 1rem;
  }
  
  .modal-footer {
    flex-direction: column;
  }
  
  .btn-secondary, .btn-primary {
    width: 100%;
  }
}
</style>