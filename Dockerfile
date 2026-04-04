# ── Stage 1: Build Frontend ────────────────────────────────────────
FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

# 禁用 Rollup 原生模組，避免跨架構問題
ENV ROLLUP_DISABLE_NATIVE=1

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./

# 使用 .env.production（VITE_API_URL=/api, VITE_WS_URL=/ws）
RUN npm run build

# ── Stage 2: Python Backend ────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# 安裝後端依賴
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端程式碼
COPY backend/ ./

# 複製前端 build 產物 → /app/static
COPY --from=frontend-builder /app/frontend/dist/ /app/static/

EXPOSE 8080

# 先跑 migration 再啟動（Render PORT 預設 8080 或 10000，用環境變數）
CMD bash -c "python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"
