#!/bin/bash

# 快速部署腳本 - 使用 ngrok 作為替代方案

set -e

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║           🚀 快速部署 - 使用 ngrok 隧道                    ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 啟動 Docker 服務
start_services() {
    print_status "啟動 Docker 服務..."
    
    # 創建 .env 如果不存在
    if [ ! -f ".env" ]; then
        cp .env.example .env
    fi
    
    # 生成 SSL 證書
    mkdir -p nginx/ssl
    if [ ! -f "nginx/ssl/cloudflare.pem" ]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/cloudflare.key \
            -out nginx/ssl/cloudflare.pem \
            -subj "/C=TW/ST=Taiwan/L=Taipei/O=QuickDeploy/CN=localhost" \
            2>/dev/null
        chmod 600 nginx/ssl/cloudflare.key
        chmod 644 nginx/ssl/cloudflare.pem
    fi
    
    # 停止現有服務
    docker-compose down 2>/dev/null || true
    
    # 啟動服務
    docker-compose up --build -d
    
    # 等待服務啟動
    print_status "等待服務啟動..."
    sleep 15
    
    # 檢查服務
    local retry=0
    while [ $retry -lt 6 ]; do
        if curl -s http://localhost/health | grep -q "healthy"; then
            print_success "Docker 服務啟動成功"
            return 0
        fi
        retry=$((retry + 1))
        print_status "等待服務啟動... ($retry/6)"
        sleep 5
    done
    
    print_warning "服務啟動可能需要更多時間，繼續執行..."
}

# 啟動 ngrok 隧道
start_ngrok() {
    print_status "啟動 ngrok 隧道..."
    
    # 停止現有的 ngrok 進程
    pkill ngrok 2>/dev/null || true
    sleep 2
    
    # 啟動 ngrok
    ngrok http 80 > /dev/null 2>&1 &
    NGROK_PID=$!
    echo $NGROK_PID > ngrok.pid
    
    # 等待 ngrok 啟動
    print_status "等待 ngrok 啟動..."
    sleep 5
    
    # 獲取公開 URL
    local retry=0
    while [ $retry -lt 10 ]; do
        NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url' 2>/dev/null || echo "")
        
        if [ "$NGROK_URL" != "" ] && [ "$NGROK_URL" != "null" ]; then
            # 轉換為 HTTPS
            NGROK_URL=$(echo $NGROK_URL | sed 's/http:/https:/')
            print_success "ngrok 隧道建立成功"
            return 0
        fi
        
        retry=$((retry + 1))
        print_status "等待 ngrok 隧道建立... ($retry/10)"
        sleep 2
    done
    
    print_warning "無法獲取 ngrok URL，檢查 ngrok 狀態"
    return 1
}

# 測試連接
test_connection() {
    print_status "測試連接..."
    
    # 測試本地
    if curl -s http://localhost/health | grep -q "healthy"; then
        print_success "本地連接正常"
    fi
    
    # 測試外部
    if [ -n "$NGROK_URL" ]; then
        local retry=0
        while [ $retry -lt 6 ]; do
            if curl -s "$NGROK_URL/health" | grep -q "healthy"; then
                print_success "外部連接測試成功"
                return 0
            fi
            retry=$((retry + 1))
            print_status "測試外部連接... ($retry/6)"
            sleep 5
        done
        print_warning "外部連接測試失敗，但服務可能仍在啟動"
    fi
}

# 顯示結果
show_results() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                     🎉 部署完成！                           ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}🌍 對外網址:${NC}"
    echo -e "${YELLOW}   $NGROK_URL${NC}"
    echo ""
    echo -e "${CYAN}📱 應用連結:${NC}"
    echo -e "   前端首頁: ${YELLOW}$NGROK_URL${NC}"
    echo -e "   主板模式: ${YELLOW}$NGROK_URL/host${NC}"
    echo -e "   用戶模式: ${YELLOW}$NGROK_URL/user${NC}"
    echo -e "   房間模式: ${YELLOW}$NGROK_URL/room${NC}"
    echo ""
    echo -e "${CYAN}🔧 管理命令:${NC}"
    echo -e "   本地訪問: ${YELLOW}http://localhost${NC}"
    echo -e "   ngrok 面板: ${YELLOW}http://localhost:4040${NC}"
    echo -e "   停止服務: ${YELLOW}./stop-quick.sh${NC}"
    echo ""
    
    # 複製到剪貼簿
    if command -v pbcopy &> /dev/null; then
        echo "$NGROK_URL" | pbcopy
        print_success "網址已複製到剪貼簿"
    fi
}

# 創建停止腳本
create_stop_script() {
    cat > stop-quick.sh << 'EOF'
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
EOF
    chmod +x stop-quick.sh
}

# 主函數
main() {
    print_header
    
    trap 'echo "部署被中斷"; exit 1' INT
    
    start_services
    start_ngrok
    test_connection
    create_stop_script
    show_results
    
    print_success "🚀 快速部署完成！服務正在背景運行..."
}

# 執行
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi