# Google Translate API 設定指南

## 步驟 1: 建立 Google Cloud 專案

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立新專案或選擇現有專案
3. 啟用 Cloud Translation API：
   - 在導航選單中，選擇「API 和服務」>「程式庫」
   - 搜尋「Cloud Translation API」
   - 點擊「啟用」

## 步驟 2: 建立 API 金鑰

1. 在 Google Cloud Console 中，前往「API 和服務」>「憑證」
2. 點擊「建立憑證」>「API 金鑰」
3. 複製產生的 API 金鑰
4. （建議）限制 API 金鑰的使用範圍：
   - 點擊 API 金鑰名稱進行編輯
   - 在「API 限制」中選擇「限制金鑰」
   - 選擇「Cloud Translation API」

## 步驟 3: 設定環境變數

將 API 金鑰添加到 `.env` 檔案中：

```bash
# 複製你的 Google API 金鑰
GOOGLE_API_KEY=你的_實際_API_金鑰

# 確認翻譯提供者設定
TRANSLATE_PROVIDER=google
```

## 步驟 4: 重啟服務

更新 `.env` 檔案後，重啟後端服務：

```bash
docker-compose restart backend
```

## 測試翻譯功能

設定完成後，你可以：

1. 在前端輸入不同語言的文字
2. 觀察是否出現翻譯結果
3. 檢查後端日誌確認翻譯 API 調用

## 成本考量

- Google Translate API 按字符收費
- 每月前 500,000 字符免費
- 超過後每 1M 字符約 $20 USD
- 可在 Google Cloud Console 設定預算警告

## 故障排除

### API 金鑰無效
- 確認 API 金鑰格式正確
- 檢查 Cloud Translation API 是否已啟用
- 確認 API 金鑰權限設定

### 翻譯請求失敗  
- 檢查網路連線
- 確認 Google Cloud 專案有足夠配額
- 查看後端日誌中的詳細錯誤訊息

### 配額超限
- 檢查 Google Cloud Console 中的用量
- 考慮升級到付費方案
- 或實作請求頻率限制