<template>
  <div class="big-subtitle-container">
    <div v-if="subtitle" class="subtitle-card">
      <div class="subtitle-header">
        <span class="speaker-name">{{ subtitle.speakerName }}</span>
        <span class="language-tag">{{ getLanguageName(subtitle.targetLang) }}</span>
      </div>
      <div class="subtitle-text">
        {{ subtitle.text }}
      </div>
      <div class="subtitle-footer">
        <span class="timestamp">{{ formatTime(subtitle.timestamp) }}</span>
      </div>
    </div>
    
    <div v-else class="subtitle-placeholder">
      <div class="placeholder-content">
        <div class="placeholder-icon">💬</div>
        <p>等待字幕...</p>
        <p class="placeholder-hint">
          當有人說話時，翻譯成 <strong>{{ getLanguageName(userLang) }}</strong> 的字幕會出現在這裡
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '../stores/session'

interface Props {
  subtitle: Message | null
  userLang: string
}

const props = defineProps<Props>()

// 語言名稱對映
const languageNames: Record<string, string> = {
  'zh-TW': '繁體中文',
  'zh-CN': '簡體中文',
  'en': 'English',
  'ja': '日本語',
  'ko': '한국어',
  'es': 'Español',
  'fr': 'Français',
  'de': 'Deutsch',
  'it': 'Italiano',
  'pt': 'Português',
  'ru': 'Русский',
  'ar': 'العربية',
  'hi': 'हिन्दी',
  'th': 'ไทย',
  'vi': 'Tiếng Việt'
}

function getLanguageName(langCode: string): string {
  return languageNames[langCode] || langCode.toUpperCase()
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 計算字幕文字大小（根據文字長度調整）
const subtitleFontSize = computed(() => {
  if (!props.subtitle?.text) return '3rem'
  
  const textLength = props.subtitle.text.length
  if (textLength < 20) return '3.5rem'
  if (textLength < 40) return '3rem'
  if (textLength < 80) return '2.5rem'
  return '2rem'
})
</script>

<style scoped>
.big-subtitle-container {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.subtitle-card {
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(20px);
  border-radius: 2rem;
  padding: 2rem 3rem;
  max-width: 90%;
  text-align: center;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
  animation: slideIn 0.5s ease-out;
}

.subtitle-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  opacity: 0.8;
}

.speaker-name {
  color: #fff;
  font-size: 1.1rem;
  font-weight: 600;
}

.language-tag {
  background: rgba(102, 126, 234, 0.8);
  color: white;
  padding: 0.3rem 0.8rem;
  border-radius: 1rem;
  font-size: 0.9rem;
  font-weight: 500;
}

.subtitle-text {
  color: #fff;
  font-size: v-bind(subtitleFontSize);
  font-weight: 700;
  line-height: 1.3;
  margin: 1.5rem 0;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.7);
  word-wrap: break-word;
  hyphens: auto;
}

.subtitle-footer {
  opacity: 0.6;
}

.timestamp {
  color: #fff;
  font-size: 0.95rem;
}

.subtitle-placeholder {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border: 2px dashed rgba(255, 255, 255, 0.3);
  border-radius: 2rem;
  padding: 4rem 3rem;
  text-align: center;
  max-width: 600px;
}

.placeholder-content {
  color: rgba(255, 255, 255, 0.8);
}

.placeholder-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  opacity: 0.6;
}

.placeholder-content p {
  margin: 0.5rem 0;
  font-size: 1.2rem;
}

.placeholder-hint {
  font-size: 1rem !important;
  opacity: 0.7;
  line-height: 1.5;
}

.placeholder-hint strong {
  color: rgba(102, 126, 234, 0.9);
  font-weight: 600;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* 響應式設計 */
@media (max-width: 768px) {
  .subtitle-card {
    padding: 1.5rem 2rem;
    border-radius: 1.5rem;
  }
  
  .subtitle-text {
    font-size: 2rem !important;
  }
  
  .placeholder-content {
    padding: 2rem 1rem;
  }
  
  .placeholder-icon {
    font-size: 3rem;
  }
}

@media (max-width: 480px) {
  .big-subtitle-container {
    padding: 1rem;
  }
  
  .subtitle-card {
    padding: 1rem 1.5rem;
    border-radius: 1rem;
  }
  
  .subtitle-text {
    font-size: 1.5rem !important;
  }
  
  .subtitle-header {
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }
}

/* 文字動畫效果 */
.subtitle-text {
  animation: textGlow 2s ease-in-out infinite alternate;
}

@keyframes textGlow {
  from {
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.7);
  }
  to {
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.7), 0 0 20px rgba(255, 255, 255, 0.1);
  }
}
</style>