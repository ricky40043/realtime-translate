#!/bin/bash

echo "🛑 停止快速部署服務..."

# 停止 Docker
docker-compose down 2>/dev/null || true
echo "✅ Docker 服務已停止"

# 停止 ngrok
if [ -f "ngrok.pid" ]; then
    kill $(cat ngrok.pid) 2>/dev/null || true
    rm -f ngrok.pid
fi
pkill ngrok 2>/dev/null || true
echo "✅ ngrok 隧道已停止"

echo "🎉 所有服務已停止"
