#!/bin/bash

echo "🚀 啟動即時翻譯字幕系統..."
echo "=================================="

# 檢查 Docker 是否運行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未運行，請先啟動 Docker"
    exit 1
fi

# 檢查 Node.js 是否安裝
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安裝，請先安裝 Node.js 18+"
    exit 1
fi

echo "✅ 環境檢查通過"
echo ""

# 步驟 1: 啟動基礎服務
echo "📦 啟動資料庫和 Redis 服務..."
docker-compose up -d db redis

echo "⏳ 等待服務初始化..."
sleep 10

# 步驟 2: 啟動後端服務
echo "🔧 啟動後端 API 服務..."
docker-compose up -d backend

echo "⏳ 等待後端服務啟動..."
sleep 5

# 檢查後端健康狀態
echo "🩺 檢查後端服務健康狀態..."
for i in {1..10}; do
    if curl -s http://localhost:8081/health > /dev/null; then
        echo "✅ 後端服務啟動成功"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ 後端服務啟動失敗"
        echo "請檢查 Docker 日誌: docker-compose logs backend"
        exit 1
    fi
    sleep 2
done

# 步驟 3: 啟動前端服務
echo "🎨 準備前端服務..."
cd frontend

# 檢查是否需要安裝依賴
if [ ! -d "node_modules" ]; then
    echo "📦 安裝前端依賴..."
    npm install
fi

echo "🎨 啟動前端開發服務器..."
echo ""
echo "=================================="
echo "🎉 系統啟動完成！"
echo "=================================="
echo ""
echo "📱 請開啟瀏覽器訪問："
echo "   主應用: http://localhost:5173"
echo ""
echo "🔧 服務端點："
echo "   後端 API: http://localhost:8081"
echo "   API 文件: http://localhost:8081/docs"
echo ""
echo "🛑 停止系統: 按 Ctrl+C 然後執行 'docker-compose down'"
echo ""
echo "🧪 開始測試吧！"
echo "=================================="

# 啟動前端 (這會阻塞直到用戶停止)
npm run dev