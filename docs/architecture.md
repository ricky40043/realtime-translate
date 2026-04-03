# Polyglot Chat — 後端完整架構文件

## 目錄
1. [系統總覽](#系統總覽)
2. [技術堆疊](#技術堆疊)
3. [資料庫結構](#資料庫結構)
4. [WebSocket 架構](#websocket-架構)
5. [語音辨識流程（STT）](#語音辨識流程stt)
6. [翻譯流程](#翻譯流程)
7. [完整語音翻譯端到端流程](#完整語音翻譯端到端流程)
8. [語言路由邏輯](#語言路由邏輯)
9. [API 端點總覽](#api-端點總覽)
10. [環境變數設定](#環境變數設定)

---

## 系統總覽

```
┌─────────────────────────────────────────────────────────┐
│                     使用者瀏覽器                         │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │  UserView    │    │  HostBoard   │                   │
│  │  (用戶視圖)  │    │  (大白板視圖)│                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                           │
│  ┌──────┴───────────────────┴───────┐                   │
│  │       SmartVoiceRecorder         │                   │
│  │  (VAD 語音活動偵測 + 自動分段)   │                   │
│  └──────────────────────────────────┘                   │
└──────────────┬──────────────┬───────────────────────────┘
               │ HTTP POST    │ WebSocket
               │ (音檔上傳)   │ (雙向即時通訊)
               ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend                        │
│                                                         │
│  ┌─────────────┐   ┌──────────────────────────────┐    │
│  │ REST API    │   │  ConnectionManager           │    │
│  │ /api/speech │   │  (WebSocket 連線管理)        │    │
│  │ /api/auth   │   │  in-memory: rooms → users    │    │
│  │ /api/rooms  │   └──────────────────────────────┘    │
│  └──────┬──────┘                                        │
│         │                                               │
│  ┌──────▼──────┐   ┌─────────────┐   ┌──────────────┐  │
│  │ Groq STT   │   │  LanguageRouter│  │ Translation  │  │
│  │ (Whisper)  │──▶│  (語言路由) │──▶│  Service     │  │
│  └────────────┘   └─────────────┘   └──────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │              PostgreSQL Database                 │   │
│  │  users / rooms / messages / translations         │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
               │ HTTP
               ▼
┌─────────────────────────────────────────────────────────┐
│                  外部 API                               │
│  Groq API (Whisper STT)  /  Google Translate (翻譯)    │
└─────────────────────────────────────────────────────────┘
```

---

## 技術堆疊

| 層級 | 技術 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| 後端 | FastAPI (Python 3.11) |
| 資料庫 | PostgreSQL |
| 語音辨識 | Groq API (`whisper-large-v3`) |
| 翻譯 | `deep-translator` → Google Translate（免費版） |
| 認證 | JWT (HS256, 7 天有效) |
| 部署 | Cloud Run (asia-east1) + Artifact Registry |

---

## 資料庫結構

```sql
-- 使用者
users
  id            UUID  PRIMARY KEY
  display_name  TEXT
  preferred_lang TEXT            -- 備用語言
  input_lang    TEXT            -- 「我要看到的字幕語言」
  output_lang   TEXT            -- 「大白板語言（我說話時）」
  created_at    TIMESTAMP

-- 房間
rooms
  id                UUID  PRIMARY KEY
  name              TEXT
  default_board_lang TEXT  DEFAULT 'en'
  created_at        TIMESTAMP

-- 語言覆寫（針對特定講者的白板語言例外）
lang_overrides
  room_id     UUID  → rooms.id
  speaker_id  UUID  → users.id
  target_lang TEXT

-- 訊息（STT 結果）
messages
  id          UUID  PRIMARY KEY
  room_id     UUID  → rooms.id
  speaker_id  UUID  → users.id
  text        TEXT
  source_lang TEXT
  is_final    BOOLEAN
  created_at  TIMESTAMP

-- 翻譯結果
translations
  message_id  UUID  → messages.id
  target_lang TEXT
  text        TEXT
  latency_ms  INT
  quality     FLOAT
```

---

## WebSocket 架構

### 連線建立

```
前端                                     後端
  │                                       │
  │── GET /ws?roomId=X&userId=Y&token=Z ─▶│
  │                                       │ 1. 驗證 JWT token
  │                                       │ 2. 加入 rooms[roomId][userId]
  │◀── { type: "connection.established" }─│
  │                                       │ 3. 廣播給房間其他人
  │◀── { type: "user.connected",          │
  │       userCount: N }        ─────────│
```

### ConnectionManager 資料結構

```python
class ConnectionManager:
    rooms: Dict[room_id, Dict[user_id, WebSocket]]
    # 範例:
    # rooms = {
    #   "room-abc": {
    #     "user-001": <WebSocket>,
    #     "user-002": <WebSocket>,
    #   }
    # }
```

### WebSocket 訊息類型

#### 後端 → 前端

| type | 說明 | 接收對象 |
|------|------|---------|
| `connection.established` | 連線成功確認 | 當事人 |
| `user.connected` | 有人進入房間 | 全房間廣播 |
| `user.disconnected` | 有人離開房間 | 全房間廣播 |
| `personal.subtitle` | 個人翻譯字幕 | 每人收到自己語言版本 |
| `board.post` | 大白板內容 | 全房間廣播（同一版本） |
| `stt.preview` | STT 預覽（speech_staged 模式） | 全房間廣播 |
| `translation.completed` | 翻譯完成通知 | 全房間廣播 |
| `pong` | 心跳回應 | 當事人 |

#### 前端 → 後端

| type | 說明 |
|------|------|
| `ping` | 心跳 keep-alive |
| `client.prefLang.update` | 更新語言偏好 |

> **注意：** 前端也會發送 `type: "speech"` 的 WebSocket 訊息，但後端目前不處理（翻譯完全透過 HTTP POST 觸發）。

### personal.subtitle 訊息格式

```json
{
  "type": "personal.subtitle",
  "messageId": "uuid",
  "targetLang": "zh-TW",
  "text": "翻譯後的文字",
  "speakerName": "用戶_abc",
  "sourceLang": "zh",
  "source": "speech",
  "timestamp": "2026-03-27T00:00:00"
}
```

### board.post 訊息格式

```json
{
  "type": "board.post",
  "messageId": "uuid",
  "speakerId": "user-uuid",
  "speakerName": "用戶_abc",
  "targetLang": "en",
  "text": "Translated text for the board",
  "sourceLang": "zh",
  "source": "speech",
  "timestamp": "2026-03-27T00:00:00"
}
```

---

## 語音辨識流程（STT）

### 前端錄音邏輯（SmartVoiceRecorder.vue）

```
使用者說話
   │
   ▼
getUserMedia() → MediaRecorder (128kbps, webm/opus)
   │
   ▼
AudioContext + AnalyserNode
   │  每 100ms 取樣音量
   ▼
VAD（語音活動偵測）邏輯:
  音量 > segmentThreshold(10%)?
     YES → 標記有語音 (hasValidSpeech = true)
     NO  → 開始計算靜音時間

  靜音持續 > segmentDelay(1s) AND 有語音?
     → processCurrentSegment() 發送音檔
     → 重新開始錄音等待下一段

  連續錄音 > maxRecordingTime(30s)?
     → 強制分段發送
```

### 音檔上傳 API

```
POST /api/speech/upload
Content-Type: multipart/form-data

Fields:
  audio:        Blob (audio/webm)
  room_id:      string
  speaker_name: string (選填)
  language_code: 不傳 → Whisper 自動偵測語言

Response:
  {
    "message_id": "uuid",      ← 翻譯任務 ID
    "transcript": "辨識文字",
    "confidence": 0.9,
    "detected_lang": "zh",
    "status": "processing"     ← 翻譯在背景執行
  }
```

### 後端 STT 處理流程

```
接收音檔
   │
   ▼
Groq API: whisper-large-v3
  - language 不傳 → 自動偵測
  - response_format: verbose_json
  - temperature: 0.0
   │
   ▼
filter_ai_default_responses()
  過濾以下情況:
  - 空白/純標點
  - 明鏡頻道推廣文字
  - 長度 ≤ 2 字元
  - 全部重複字元
   │
   ├─ 過濾掉 → 回傳 status: "filtered", transcript: ""
   │
   └─ 通過  → 存入 DB (messages table)
              → 啟動 BackgroundTask: process_speech_translation()
              → 立即回傳 status: "processing"
```

---

## 翻譯流程

### 翻譯服務架構

```
translation_service.batch_translate(text, target_langs, source_lang)
   │
   ├─ TRANSLATE_PROVIDER=free (預設)
   │     └─ FreeTranslateService
   │           └─ deep-translator → GoogleTranslator
   │                 _convert_lang_code():
   │                   "zh-TW" → "zh-TW"
   │                   "zh-CN" → "zh-CN"
   │                   "en"    → "en"
   │                   "ja"    → "ja"
   │                   (其他帶 - 的代碼截取主語系)
   │
   ├─ TRANSLATE_PROVIDER=google (需 GOOGLE_API_KEY)
   │     └─ Google Translate v2 REST API
   │
   ├─ TRANSLATE_PROVIDER=google_v3 (需 GCP 服務帳號)
   │     └─ Google Cloud Translation v3
   │
   └─ TRANSLATE_PROVIDER=mock (測試用)
         └─ MockTranslationService (硬編碼對照表)
```

### 翻譯 double-pass 容錯機制

```python
translated = GoogleTranslator(source=src, target=tgt).translate(text)

# 如果翻譯前後完全一樣（可能是 STT 語言偵測錯誤）
if translated == text and tgt != src:
    # 改用 auto 重試一次
    translated = GoogleTranslator(source='auto', target=tgt).translate(text)
```

---

## 完整語音翻譯端到端流程

```
┌─────────────────────────────────────────────────────────────┐
│ 情境：房間有 User A（看繁中字幕）和 User B（看英文字幕）     │
│       User A 說了一句話                                      │
└─────────────────────────────────────────────────────────────┘

[前端 - User A 的瀏覽器]
1. SmartVoiceRecorder 偵測到靜音結束
2. 封裝 audio.webm → 呼叫 speechApi.upload()

[HTTP POST /api/speech/upload]
3. Groq whisper-large-v3 辨識語音
   → transcript: "你好，請問幾點了？"
   → detected_lang: "zh"

4. filter_ai_default_responses() 通過

5. DB INSERT INTO messages (room_id, speaker_id, text, source_lang)

6. 立即回傳 { status: "processing" } 給前端

[BackgroundTask: process_speech_translation()]
7. ConnectionManager.get_room_users(room_id)
   → [user_A_id, user_B_id]

8. LanguageRouter.get_all_target_languages()
   → 讀取每位用戶的 input_lang：
        User A: input_lang = "zh-TW"
        User B: input_lang = "en"
   → 讀取 User A 的 output_lang（白板語言）:
        User A: output_lang = "en"
   → 所有目標語言 = {"zh-TW", "en"}

9. translation_service.batch_translate(
     text = "你好，請問幾點了？",
     target_langs = ["zh-TW", "en"],
     source_lang = "zh"
   )
   → "zh-TW": "你好，請問幾點了？"（繁中，幾乎原文）
   → "en":    "Hello, what time is it?"

10. DB INSERT INTO translations (message_id, target_lang, text)

[broadcast_speech_translations()]
11. 發送 personal.subtitle 給每個人（各自的語言版本）:
    → User A: targetLang="zh-TW", text="你好，請問幾點了？"
    → User B: targetLang="en",    text="Hello, what time is it?"

12. 發送 board.post 給全房間（User A 的 output_lang="en"）:
    → 所有人: targetLang="en", text="Hello, what time is it?"

[前端 - User A 的瀏覽器]
13. 收到 personal.subtitle (targetLang="zh-TW")
    → message.targetLang === inputLang.value ("zh-TW" === "zh-TW") ✓
    → 顯示中文字幕

14. 收到 board.post → UserView 忽略（只給 HostBoard 顯示）

[前端 - User B 的瀏覽器]
15. 收到 personal.subtitle (targetLang="en")
    → message.targetLang === inputLang.value ("en" === "en") ✓
    → 顯示英文字幕

16. 收到 board.post → UserView 忽略

[HostBoard 大白板]
17. 收到 board.post (targetLang="en", text="Hello, what time is it?")
    → 顯示在大白板上
```

---

## 語言路由邏輯

```python
# LanguageRouter.get_target_languages(room_id, speaker_id, online_users)

個人字幕目標語言（personal）:
  → 遍歷所有在線用戶
  → 收集每人的 input_lang（我要看到的字幕語言）
  → 去重 → 得到需要翻譯的語言集合

大白板目標語言（board）:
  → 讀取講者的 output_lang（大白板語言）
  → 若未設定 → 用 lang_overrides 或 room.default_board_lang

最終翻譯目標 = personal ∪ board（聯集，去重）
```

### 語言代碼規則

| 用途 | 格式 | 範例 |
|------|------|------|
| `input_lang` / `output_lang` DB | 短代碼 | `zh-TW`, `en`, `ja` |
| Groq STT language 參數 | Whisper 代碼 | `zh`, `en`, `ja`（或不傳） |
| Google Translate target | 短代碼 | `zh-TW`, `en`, `ja` |

---

## API 端點總覽

### 認證

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/auth/guest` | 建立訪客用戶，取得 JWT token |
| PUT  | `/api/auth/update-langs` | 更新用戶的 input_lang / output_lang |

### 房間

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/rooms` | 建立房間 |
| GET  | `/api/rooms/{id}` | 取得房間資訊 |
| PUT  | `/api/rooms/{id}/board-lang` | 更新白板預設語言 |
| PUT  | `/api/rooms/{id}/overrides` | 更新講者語言覆寫 |

### 語音

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/speech/upload` | 上傳音檔 → STT → 翻譯廣播 |
| POST | `/api/speech-staged/stt-only` | 只做 STT，回傳辨識結果 |
| POST | `/api/speech-staged/translate-stt` | 對已辨識文字做翻譯廣播 |

### WebSocket

| 路徑 | 說明 |
|------|------|
| `/ws?roomId=&userId=&token=` | 主要 WebSocket 連線端點 |

---

## 環境變數設定

```env
# 資料庫
POSTGRES_URL=postgres://user:pass@host:5433/dbname

# JWT
JWT_SECRET=your_secret_key

# STT 服務
STT_PROVIDER=groq          # groq / google / google_v1 / azure / mock / free
GROQ_API_KEY=gsk_...

# 翻譯服務
TRANSLATE_PROVIDER=free    # free / google / google_v3 / azure / mock
GOOGLE_API_KEY=            # TRANSLATE_PROVIDER=google 時需要
AZURE_TRANSLATOR_KEY=      # TRANSLATE_PROVIDER=azure 時需要
AZURE_TRANSLATOR_ENDPOINT= # TRANSLATE_PROVIDER=azure 時需要
```

### STT Provider 選擇邏輯

```
GROQ_API_KEY 有設定?
  YES → 使用 Groq (whisper-large-v3)  ← 目前使用
  NO  → 自動降級為 mock

TRANSLATE_PROVIDER=free?
  YES → deep-translator (不需 API Key)  ← 目前使用
  NO, GOOGLE_API_KEY 有設定 → Google Translate v2
  都沒有 → 自動降級為 mock
```
