#!/bin/bash

# 快速啟動 nginx 反向代理服務

set -e

echo "🚀 啟動 nginx 反向代理服務..."

# 檢查是否存在 SSL 證書，沒有則生成臨時證書
if [ ! -f "nginx/ssl/cloudflare.pem" ]; then
    echo "📋 生成臨時 SSL 證書..."
    mkdir -p nginx/ssl
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/ssl/cloudflare.key \
        -out nginx/ssl/cloudflare.pem \
        -subj "/C=TW/ST=Taiwan/L=Taipei/O=DevTest/CN=localhost" \
        2>/dev/null
    chmod 600 nginx/ssl/cloudflare.key
    chmod 644 nginx/ssl/cloudflare.pem
    echo "✅ 臨時證書生成完成"
fi

# 停止現有容器（如果有的話）
echo "🛑 停止現有服務..."
docker-compose down 2>/dev/null || true

# 啟動服務
echo "▶️  啟動服務..."
docker-compose up --build -d

# 等待服務啟動
echo "⏳ 等待服務啟動..."
sleep 15

# 檢查服務狀態
echo "🔍 檢查服務狀態..."
docker-compose ps

# 測試連接
echo "🧪 測試服務連接..."
if curl -s http://localhost/health | grep -q "healthy"; then
    echo "✅ HTTP 服務正常"
else
    echo "⚠️  HTTP 服務可能未就緒，請稍後再試"
fi

if curl -k -s https://localhost/health | grep -q "healthy"; then
    echo "✅ HTTPS 服務正常"
else
    echo "⚠️  HTTPS 服務可能未就緒，請稍後再試"
fi

echo ""
echo "🎉 服務啟動完成！"
echo ""
echo "📋 訪問地址："
echo "  前端: http://localhost"
echo "  前端 (HTTPS): https://localhost"
echo "  API: http://localhost/api"
echo "  健康檢查: http://localhost/health"
echo ""
echo "🔧 管理命令："
echo "  查看日誌: docker-compose logs -f"
echo "  停止服務: docker-compose down"
echo "  重啟服務: docker-compose restart"