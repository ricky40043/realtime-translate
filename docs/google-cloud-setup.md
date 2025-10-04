# Google Cloud Translation & Speech API 設定指南

## 🎯 完整設定流程

### 步驟 1: 建立 Google Cloud 專案

1. **前往 Google Cloud Console**
   - 訪問：https://console.cloud.google.com/
   - 登入你的 Google 帳號

2. **建立新專案**
   - 點擊頂部的專案選擇器
   - 點擊「新增專案」
   - 輸入專案名稱（例如：`realtime-translate`）
   - 記錄專案 ID（系統自動生成）

### 步驟 2: 啟用必要的 API

1. **啟用 Cloud Translation API**
   - 在左側選單選擇「API 和服務」→「程式庫」
   - 搜尋「Cloud Translation API」
   - 點擊進入並按「啟用」

2. **啟用 Cloud Speech-to-Text API**
   - 同樣在「程式庫」中搜尋「Cloud Speech-to-Text API」
   - 點擊進入並按「啟用」

### 步驟 3: 建立 Service Account

1. **前往 IAM 和管理**
   - 左側選單選擇「IAM 和管理」→「服務帳戶」
   - 點擊「建立服務帳戶」

2. **設定服務帳戶**
   - 服務帳戶名稱：`realtime-translate-service`
   - 服務帳戶 ID：會自動生成
   - 描述：`用於即時翻譯系統的服務帳戶`
   - 點擊「建立並繼續」

3. **授予權限**
   - 角色 1：`Cloud Translation API User`
   - 角色 2：`Cloud Speech Client`
   - 點擊「繼續」然後「完成」

### 步驟 4: 下載 Service Account Key

1. **產生金鑰檔案**
   - 在服務帳戶列表中找到剛建立的帳戶
   - 點擊服務帳戶名稱進入詳細頁面
   - 切換到「金鑰」分頁
   - 點擊「新增金鑰」→「建立新金鑰」
   - 選擇「JSON」格式
   - 點擊「建立」

2. **保存金鑰檔案**
   - 下載的 JSON 檔案包含認證資訊
   - 將檔案重新命名為 `service-account.json`
   - 移動到專案根目錄

### 步驟 5: 設定環境變數

1. **更新 .env 檔案**
   ```bash
   # Google Cloud 設定
   GOOGLE_CLOUD_PROJECT=your-actual-project-id
   GOOGLE_APPLICATION_CREDENTIALS=./service-account.json
   
   # 使用新的服務提供者
   TRANSLATE_PROVIDER=google_v3
   STT_PROVIDER=google_v1
   ```

2. **確認檔案路徑**
   ```
   你的專案/
   ├── service-account.json    ← JSON 金鑰檔案
   ├── .env                    ← 環境變數
   ├── backend/
   └── frontend/
   ```

### 步驟 6: 重啟服務

```bash
# 重新建構並啟動後端（安裝新的 Google Cloud 依賴）
docker-compose down
docker-compose up --build backend

# 檢查服務是否正常
curl http://localhost:8081/health
```

## 🧪 測試設定

### 測試翻譯功能
```bash
# 建立測試用戶
RESPONSE=$(curl -s -X POST http://localhost:8081/api/auth/guest \
  -H "Content-Type: application/json" \
  -d '{"display_name":"測試用戶","preferred_lang":"zh-TW"}')

TOKEN=$(echo $RESPONSE | python3 -c "import json, sys; print(json.load(sys.stdin)['token'])")

# 建立測試房間
ROOM_RESPONSE=$(curl -s -X POST http://localhost:8081/api/rooms \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"測試房間","default_board_lang":"en"}')

ROOM_ID=$(echo $ROOM_RESPONSE | python3 -c "import json, sys; print(json.load(sys.stdin)['id'])")

# 測試翻譯
curl -s -X POST http://localhost:8081/api/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"room_id\":\"$ROOM_ID\",\"text\":\"今天天氣很好，適合外出遊玩\",\"is_final\":true}"
```

### 測試語音功能
```bash
# 建立測試音頻檔案
echo "測試音頻" > test_audio.webm

# 測試語音轉文字
curl -s -X POST http://localhost:8081/api/speech/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "room_id=$ROOM_ID" \
  -F "language_code=zh-TW" \
  -F "audio=@test_audio.webm;type=audio/webm"
```

## 📊 監控使用量

### 設定預算警告

1. **前往計費頁面**
   - Google Cloud Console → 計費 → 預算和快訊
   - 點擊「建立預算」

2. **設定預算**
   - 預算名稱：`Translation API Budget`
   - 專案：選擇你的專案
   - 時間範圍：每月
   - 預算金額：$50 USD（建議）

3. **設定快訊**
   - 快訊閾值：50%, 90%, 100%
   - 電子郵件通知：輸入你的信箱

### 查看使用量

1. **API 使用情況**
   - Google Cloud Console → API 和服務 → 儀表板
   - 查看 Translation API 和 Speech API 的使用量

2. **計費詳情**
   - 計費 → 報表
   - 按服務篩選查看詳細費用

## ⚡ 效能優化建議

### 1. 快取翻譯結果
```python
# 在實際應用中加入 Redis 快取
translation_cache = {}

if text in translation_cache:
    return translation_cache[text]
else:
    result = await translate(text)
    translation_cache[text] = result
    return result
```

### 2. 批次處理
```python
# 收集多個翻譯請求一起處理
pending_translations = []
# ... 收集請求 ...
results = await batch_translate(pending_translations)
```

### 3. 設定配額限制
- 在 Google Cloud Console 中設定每日/每月使用上限
- 避免意外的高額費用

## 🔒 安全性注意事項

1. **保護 Service Account Key**
   - 不要將 JSON 檔案提交到 Git
   - 在 .gitignore 中加入 `service-account.json`
   - 生產環境使用環境變數或機密管理服務

2. **限制權限**
   - 只授予必要的 API 權限
   - 定期檢查和輪換金鑰

3. **監控異常使用**
   - 設定預算警告
   - 監控 API 調用模式

## 🚀 完成！

設定完成後，你的系統將使用：
- ✅ **Google Cloud Translation API v3**：高品質文字翻譯
- ✅ **Google Cloud Speech-to-Text API v1**：準確的語音識別
- ✅ **即時串流支援**：適合即時翻譯場景
- ✅ **自動語言檢測**：智慧識別輸入語言

現在可以享受專業級的翻譯和語音識別服務了！