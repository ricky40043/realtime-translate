#!/bin/bash

# 獲取當前 ngrok 網址的腳本

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 檢查 ngrok 隧道狀態...${NC}"

# 檢查 ngrok 是否運行
if ! pgrep -f "ngrok" > /dev/null; then
    echo -e "${RED}❌ ngrok 未運行${NC}"
    echo "請先啟動 ngrok: ngrok http 80"
    exit 1
fi

# 檢查 ngrok API 是否可訪問
if ! curl -s http://localhost:4040/api/tunnels > /dev/null; then
    echo -e "${RED}❌ 無法連接到 ngrok API${NC}"
    echo "請確認 ngrok 正常運行"
    exit 1
fi

# 獲取 ngrok 網址
URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url' 2>/dev/null)

if [ "$URL" = "null" ] || [ -z "$URL" ]; then
    echo -e "${RED}❌ 無法獲取 ngrok 網址${NC}"
    echo "請檢查 ngrok 隧道是否正常建立"
    exit 1
fi

echo -e "${GREEN}✅ ngrok 隧道正常運行${NC}"
echo ""
echo -e "${YELLOW}🌐 當前網址:${NC}"
echo -e "${GREEN}$URL${NC}"
echo ""

# 嘗試複製到剪貼簿
if command -v pbcopy &> /dev/null; then
    echo "$URL" | pbcopy
    echo -e "${GREEN}✅ 網址已複製到 macOS 剪貼簿${NC}"
elif command -v xclip &> /dev/null; then
    echo "$URL" | xclip -selection clipboard
    echo -e "${GREEN}✅ 網址已複製到 Linux 剪貼簿${NC}"
else
    echo -e "${YELLOW}💡 請手動複製上方網址${NC}"
fi

echo ""
echo -e "${BLUE}📱 測試連結:${NC}"
echo "  翻譯首頁: $URL/room"
echo "  用戶頁面: $URL/user"
echo "  主板頁面: $URL/host"
echo ""

# 測試連接
echo -e "${BLUE}🧪 測試連接...${NC}"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL/health" 2>/dev/null)

if [ "$HTTP_STATUS" = "200" ]; then
    echo -e "${GREEN}✅ 服務連接正常 (HTTP $HTTP_STATUS)${NC}"
else
    echo -e "${YELLOW}⚠️  服務可能未就緒 (HTTP $HTTP_STATUS)${NC}"
    echo "請檢查 Docker 服務和前端開發服務是否正常運行"
fi