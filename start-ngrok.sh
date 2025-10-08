#!/bin/bash

# 快速啟動 ngrok 的腳本

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 快速啟動 ngrok...${NC}"

# 檢查服務狀態
echo "檢查服務狀態..."

# 檢查 Docker 服務
if ! docker-compose ps | grep "Up" > /dev/null; then
    echo -e "${YELLOW}⚠️  Docker 服務未運行，正在啟動...${NC}"
    docker-compose up -d
    sleep 5
fi

# 檢查前端服務
if ! pgrep -f "npm run dev" > /dev/null; then
    echo -e "${YELLOW}⚠️  前端服務未運行，正在啟動...${NC}"
    cd frontend && npm run dev > ../frontend.log 2>&1 &
    cd ..
    sleep 5
fi

# 停止現有 ngrok (如果有的話)
pkill ngrok 2>/dev/null || true
sleep 2

# 啟動 ngrok
echo -e "${BLUE}🌐 啟動 ngrok 隧道...${NC}"
ngrok http 80 > ngrok.log 2>&1 &

# 等待 ngrok 啟動
sleep 8

# 獲取並顯示網址
echo -e "${GREEN}✅ ngrok 已啟動！${NC}"
echo ""

# 使用 get-url.sh 顯示詳細信息
if [ -f "get-url.sh" ]; then
    ./get-url.sh
else
    # 簡單版本的網址獲取
    URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url' 2>/dev/null)
    if [ "$URL" != "null" ] && [ -n "$URL" ]; then
        echo -e "${GREEN}🌐 網址: $URL${NC}"
    else
        echo -e "${YELLOW}⚠️  請稍候再試或手動檢查 ngrok 狀態${NC}"
    fi
fi