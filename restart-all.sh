#!/bin/bash

# 重啟所有服務的腳本

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    🔄 重啟所有服務                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 停止現有服務
echo -e "${YELLOW}🛑 停止現有服務...${NC}"

echo "  停止 ngrok..."
pkill ngrok 2>/dev/null || true

echo "  停止前端開發服務..."
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true

echo "  停止 Docker 服務..."
docker-compose down

echo -e "${GREEN}✅ 所有服務已停止${NC}"
echo ""

# 啟動 Docker 服務
echo -e "${BLUE}🐳 啟動 Docker 服務...${NC}"
docker-compose up --build -d

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Docker 服務啟動失敗${NC}"
    exit 1
fi

echo "  等待 Docker 服務啟動..."
sleep 8

# 檢查 Docker 服務狀態
echo "  檢查 Docker 服務狀態:"
docker-compose ps

echo -e "${GREEN}✅ Docker 服務已啟動${NC}"
echo ""

# 檢查前端 Docker 服務
echo -e "${BLUE}⚛️  檢查前端 Docker 服務...${NC}"

echo "  等待前端容器完全啟動..."
sleep 8

# 檢查前端容器是否運行
if docker-compose ps frontend | grep -q "Up"; then
    echo -e "${GREEN}✅ 前端 Docker 服務已啟動${NC}"
    
    # 檢查前端服務是否可訪問
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 前端服務可正常訪問${NC}"
    else
        echo -e "${YELLOW}⚠️  前端服務正在啟動中...${NC}"
        echo "  可查看容器日誌: docker-compose logs frontend"
    fi
else
    echo -e "${RED}❌ 前端 Docker 服務啟動失敗${NC}"
    echo "請執行 'docker-compose logs frontend' 查看錯誤信息"
fi
echo ""

# 啟動 ngrok
echo -e "${BLUE}🌐 啟動 ngrok 隧道...${NC}"
ngrok http 80 > ngrok.log 2>&1 &

echo "  等待 ngrok 隧道建立..."
sleep 8

# 檢查 ngrok 狀態
if pgrep -f "ngrok" > /dev/null; then
    echo -e "${GREEN}✅ ngrok 隧道已啟動${NC}"
else
    echo -e "${RED}❌ ngrok 啟動失敗${NC}"
    echo "請檢查 ngrok.log 獲取錯誤信息"
    exit 1
fi
echo ""

# 顯示新網址
echo -e "${CYAN}🎉 所有服務重啟完成！${NC}"
echo ""

if [ -f "get-url.sh" ]; then
    ./get-url.sh
else
    # 如果 get-url.sh 不存在，直接獲取網址
    URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url' 2>/dev/null)
    if [ "$URL" != "null" ] && [ -n "$URL" ]; then
        echo -e "${GREEN}🌐 新網址: $URL${NC}"
        echo "$URL" | pbcopy 2>/dev/null && echo -e "${GREEN}✅ 已複製到剪貼簿${NC}"
    else
        echo -e "${YELLOW}⚠️  無法獲取 ngrok 網址，請手動檢查${NC}"
    fi
fi

echo ""
echo -e "${BLUE}📋 服務狀態總結:${NC}"
echo "  Docker: $(docker-compose ps --services | wc -l | tr -d ' ') 個服務運行中"
echo "  前端: $(docker-compose ps frontend | grep -q "Up" && echo "✅ Docker容器運行中" || echo "❌ Docker容器未運行")"
echo "  ngrok: $(pgrep -f "ngrok" > /dev/null && echo "✅ 運行中" || echo "❌ 未運行")"
echo ""
echo -e "${YELLOW}💡 如有問題，請檢查日誌文件:${NC}"
echo "  docker-compose logs frontend - 前端服務日誌"
echo "  ngrok.log - ngrok 日誌"
echo "  docker-compose logs - 所有 Docker 服務日誌"