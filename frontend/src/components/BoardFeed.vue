<template>
  <div class="board-feed">
    <div v-if="messages.length === 0" class="empty-state">
      <div class="empty-icon">📢</div>
      <p>尚無訊息</p>
      <p class="empty-hint">所有訊息會翻譯成 <strong>{{ getLanguageName(boardLang) }}</strong> 顯示在這裡</p>
    </div>
    
    <div v-else class="messages-container" ref="messagesContainer">
      <div 
        v-for="message in sortedMessages" 
        :key="message.id"
        class="message-card"
        :class="{ 'message-new': isNewMessage(message) }"
      >
        <div class="message-header">
          <div class="speaker-info">
            <div class="speaker-avatar">
              {{ getAvatarText(message.speakerName || '未知用戶') }}
            </div>
            <div class="speaker-details">
              <span class="speaker-name">{{ message.speakerName || '未知用戶' }}</span>
              <span class="message-time">{{ formatTime(message.timestamp || new Date().toISOString()) }}</span>
            </div>
          </div>
          <div class="message-meta">
            <span class="language-info">
              {{ getLanguageName(message.sourceLang || '') }} → {{ getLanguageName(message.targetLang || '') }}
            </span>
          </div>
        </div>
        
        <div class="message-content">
          <p class="message-text">{{ message.text }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, watch } from 'vue'
import type { Message } from '../stores/session'

interface Props {
  messages: Message[]
  boardLang: string
}

const props = defineProps<Props>()

const messagesContainer = ref<HTMLElement | null>(null)
const newMessageIds = ref<Set<string>>(new Set())

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

// 計算屬性
const sortedMessages = computed(() => {
  return [...props.messages].sort((a, b) => {
    const timeA = new Date(a.timestamp || new Date()).getTime()
    const timeB = new Date(b.timestamp || new Date()).getTime()
    return timeA - timeB
  })
})

// 監聽訊息變化，自動滾動到底部
watch(() => props.messages.length, async (newLength, oldLength) => {
  if (newLength > oldLength) {
    // 標記新訊息
    const newMessage = props.messages[props.messages.length - 1]
    if (newMessage) {
      newMessageIds.value.add(newMessage.id)
      
      // 3秒後移除新訊息標記
      setTimeout(() => {
        newMessageIds.value.delete(newMessage.id)
      }, 3000)
    }
    
    // 滾動到底部
    await nextTick()
    scrollToBottom()
  }
})

function getLanguageName(langCode: string): string {
  return languageNames[langCode] || langCode.toUpperCase()
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMinutes = Math.floor(diffMs / 60000)
  
  if (diffMinutes < 1) {
    return '剛剛'
  } else if (diffMinutes < 60) {
    return `${diffMinutes} 分鐘前`
  } else {
    return date.toLocaleTimeString('zh-TW', {
      hour: '2-digit',
      minute: '2-digit'
    })
  }
}

function getAvatarText(speakerName: string): string {
  if (!speakerName) return '?'
  
  // 中文名字取最後一個字
  if (/[\u4e00-\u9fff]/.test(speakerName)) {
    return speakerName.slice(-1)
  }
  
  // 英文名字取首字母
  const words = speakerName.split(' ')
  if (words.length >= 2 && words[0] && words[1]) {
    return words[0][0].toUpperCase() + words[1][0].toUpperCase()
  }
  
  return speakerName.length > 0 ? speakerName[0].toUpperCase() : '?'
}

function isNewMessage(message: Message): boolean {
  return newMessageIds.value.has(message.id)
}

function scrollToBottom(): void {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 顏色生成函數（根據講者名稱生成一致的顏色）
function getSpeakerColor(speakerName: string): string {
  // 防止 speakerName 為 undefined 或 null
  if (!speakerName) {
    return '#6c757d' // 預設灰色
  }
  
  const colors = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', 
    '#FECA57', '#FF9FF3', '#54A0FF', '#5F27CD',
    '#00D2D3', '#FF9F43', '#54A0FF', '#1DD1A1'
  ]
  
  let hash = 0
  const safeSpeakerName = speakerName || '未知用戶'
  for (let i = 0; i < safeSpeakerName.length; i++) {
    hash = safeSpeakerName.charCodeAt(i) + ((hash << 5) - hash)
  }
  
  return colors[Math.abs(hash) % colors.length]
}
</script>

<style scoped>
.board-feed {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #666;
  text-align: center;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-state p {
  margin: 0.5rem 0;
  font-size: 1.1rem;
}

.empty-hint {
  font-size: 0.9rem !important;
  opacity: 0.7;
  line-height: 1.5;
}

.empty-hint strong {
  color: #667eea;
  font-weight: 600;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 0;
  scroll-behavior: smooth;
}

.messages-container::-webkit-scrollbar {
  width: 6px;
}

.messages-container::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.messages-container::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.message-card {
  background: white;
  border-radius: 1rem;
  padding: 1rem;
  margin-bottom: 1rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #e9ecef;
  transition: all 0.3s ease;
}

.message-new {
  animation: messageSlideIn 0.5s ease-out;
  border-left-color: #28a745;
  box-shadow: 0 4px 16px rgba(40, 167, 69, 0.2);
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.75rem;
}

.speaker-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.speaker-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: v-bind('getSpeakerColor(messages[0]?.speakerName || "未知用戶")');
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.speaker-details {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.speaker-name {
  font-weight: 600;
  color: #333;
  font-size: 0.95rem;
}

.message-time {
  font-size: 0.8rem;
  color: #666;
}

.message-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.25rem;
}

.language-info {
  font-size: 0.75rem;
  color: #888;
  background: #f8f9fa;
  padding: 0.25rem 0.5rem;
  border-radius: 0.5rem;
  white-space: nowrap;
}

.message-content {
  margin-left: 3rem;
}

.message-text {
  margin: 0;
  color: #333;
  line-height: 1.5;
  font-size: 1rem;
  word-wrap: break-word;
  hyphens: auto;
}

@keyframes messageSlideIn {
  from {
    opacity: 0;
    transform: translateX(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* 響應式設計 */
@media (max-width: 768px) {
  .message-card {
    padding: 0.75rem;
    border-radius: 0.75rem;
  }
  
  .message-header {
    flex-direction: column;
    gap: 0.5rem;
    align-items: flex-start;
  }
  
  .message-meta {
    align-items: flex-start;
  }
  
  .message-content {
    margin-left: 0;
    margin-top: 0.5rem;
  }
  
  .speaker-avatar {
    width: 32px;
    height: 32px;
    font-size: 0.8rem;
  }
}

@media (max-width: 480px) {
  .message-card {
    padding: 0.5rem;
    margin-bottom: 0.75rem;
  }
  
  .speaker-info {
    gap: 0.5rem;
  }
  
  .language-info {
    font-size: 0.7rem;
  }
  
  .message-text {
    font-size: 0.9rem;
  }
}
</style>