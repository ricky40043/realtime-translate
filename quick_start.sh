#!/bin/bash

echo "🚀 快速啟動系統（混合模式）..."
echo "=================================="

# 啟動後端服務 (Docker)
echo "📦 啟動後端服務..."
docker-compose up -d db redis backend

echo "⏳ 等待後端啟動..."
sleep 15

# 檢查後端
if curl -s http://localhost:8081/health > /dev/null; then
    echo "✅ 後端服務運行正常"
else
    echo "❌ 後端服務啟動失敗"
    exit 1
fi

# 啟動前端 (本地 npm)
echo "🎨 啟動前端服務 (本地)..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "📦 安裝前端依賴..."
    npm install
fi

echo "🎯 啟動前端開發服務器..."
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
echo ""
echo "🛑 停止後端: docker-compose down"
echo "🛑 停止前端: 按 Ctrl+C"
echo ""
echo "🧪 開始測試吧！"
echo "=================================="

# 啟動前端 (會阻塞直到停止)
npm run dev