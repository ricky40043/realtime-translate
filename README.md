# 即時翻譯字幕系統

支援語音→STT→翻譯→多人即時字幕與「主板」統一語言顯示的系統。

## 功能特色

- 房間頁：麥克風上傳或純打字
- 個人視圖：翻成「我的語言」大字字幕
- 主板視圖：翻成「主板語言」，可 per-speaker 覆寫
- 即時 WebSocket 通訊
- 支援多種翻譯服務（Google Translate / Azure Translator）

## 技術架構

- 前端：Vue 3 + Vite + Pinia + Vue Router + WebSocket
- 後端：Python FastAPI + Uvicorn + Redis + PostgreSQL
- 資料庫：PostgreSQL（訊息與翻譯版本）
- 事件：Redis Pub/Sub

## 快速開始

1. 複製環境變數檔案：
```bash
cp .env.example .env
```

2. 啟動服務：
```bash
docker-compose up -d
```

3. 安裝前端依賴：
```bash
cd frontend
npm install
npm run dev
```

4. 啟動後端：
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## 專案結構

```
realtime-translate/
  frontend/           # Vue 3 前端
  backend/            # Python FastAPI 後端
  docker/             # Docker 設定
  docs/               # 文件
  .env.example        # 環境變數範例
  README.md           # 專案說明
```