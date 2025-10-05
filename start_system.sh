#!/bin/bash

echo "🚀 啟動即時翻譯字幕系統..."
echo "=================================="

# 檢查 Docker 是否運行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未運行，請先啟動 Docker"
    exit 1
fi

# 檢查 Node.js 是否安裝
if ! command -v npm &> /dev/null; then
    echo "❌ Node.js/npm 未安裝，請先安裝 Node.js"
    exit 1
fi

echo "✅ 環境檢查通過"
echo ""

# 停止現有容器
echo "🧹 清理現有容器..."
docker-compose down

# 啟動後端服務 (Docker)
echo "📦 啟動後端服務 (Docker)..."
docker-compose up -d db redis backend

echo "⏳ 等待後端服務啟動..."
sleep 15

# 檢查後端健康狀態
echo "🩺 檢查後端服務..."
for i in {1..5}; do
    if curl -s http://localhost:8081/health > /dev/null; then
        echo "✅ 後端服務運行正常"
        break
    fi
    if [ $i -eq 5 ]; then
        echo "❌ 後端服務未響應"
        echo "後端日誌:"
        docker-compose logs backend
        exit 1
    fi
    sleep 3
done

# 啟動前端 (本地 npm)
echo "🎨 啟動前端服務 (本地 npm)..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "📦 安裝前端依賴..."
    npm install
fi

echo ""
echo "=================================="
echo "🎉 系統啟動完成！"
echo "=================================="
echo ""
echo "📱 請開啟瀏覽器訪問："
echo "   🏠 主應用: http://localhost:5173"
echo "   👑 主板頁面: http://localhost:5173/host/test-room"
echo "   👤 用戶頁面: http://localhost:5173/user/test-room"
echo ""
echo "🔧 服務狀態："
echo "   🔌 後端 API: http://localhost:8081 (Docker)"
echo "   🎨 前端服務: http://localhost:5173 (本地)"
echo "   💚 健康檢查: http://localhost:8081/health"
echo "   📚 API 文件: http://localhost:8081/docs"
echo ""
echo "📊 實用命令："
echo "   查看後端日誌: docker-compose logs backend"
echo "   重啟後端: docker-compose restart backend"
echo "   停止後端: docker-compose down"
echo "   停止前端: 按 Ctrl+C"
echo ""
echo "🧪 測試建議："
echo "   1. 開啟主板頁面建立房間"
echo "   2. 複製房間ID到用戶頁面"
echo "   3. 測試雙語言設定功能"
echo "   4. 驗證即時訊息同步"
echo ""
echo "🎯 啟動前端開發服務器..."
echo "=================================="

# 啟動前端 (會阻塞直到停止) - 已經在frontend目錄中
npm run dev