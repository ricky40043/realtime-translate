#!/bin/bash

# 一鍵部署腳本 - 自動創建 Cloudflare Tunnel 並部署應用

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# 全局變數
TUNNEL_NAME="polyglot-chat-$(date +%s)"
TUNNEL_URL=""
TUNNEL_ID=""
CONFIG_FILE="$HOME/.cloudflared/config.yml"

print_header() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                🚀 一鍵部署多語言聊天應用                      ║"
    echo "║              自動 Cloudflare Tunnel + Docker               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
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

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# 檢查依賴
check_dependencies() {
    print_step "檢查系統依賴..."
    
    local missing_deps=()
    
    if ! command -v docker &> /dev/null; then
        missing_deps+=("docker")
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        missing_deps+=("docker-compose")
    fi
    
    if ! command -v cloudflared &> /dev/null; then
        missing_deps+=("cloudflared")
    fi
    
    if ! command -v jq &> /dev/null; then
        print_warning "jq 未安裝，正在安裝..."
        brew install jq
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "缺少依賴: ${missing_deps[*]}"
        echo "請先安裝缺少的依賴"
        exit 1
    fi
    
    print_success "所有依賴檢查完成"
}

# 檢查 Cloudflare 登入狀態
check_cloudflare_auth() {
    print_step "檢查 Cloudflare 認證..."
    
    if ! cloudflared tunnel list &> /dev/null; then
        print_warning "需要登入 Cloudflare"
        print_status "正在打開瀏覽器進行登入..."
        cloudflared tunnel login
        
        if ! cloudflared tunnel list &> /dev/null; then
            print_error "Cloudflare 登入失敗"
            exit 1
        fi
    fi
    
    print_success "Cloudflare 認證通過"
}

# 創建 Cloudflare Tunnel
create_tunnel() {
    print_step "創建 Cloudflare Tunnel..."
    
    # 創建新的 tunnel
    print_status "創建 tunnel: $TUNNEL_NAME"
    TUNNEL_OUTPUT=$(cloudflared tunnel create $TUNNEL_NAME 2>&1)
    
    if [ $? -ne 0 ]; then
        print_error "Tunnel 創建失敗: $TUNNEL_OUTPUT"
        exit 1
    fi
    
    # 獲取 tunnel ID
    TUNNEL_ID=$(echo "$TUNNEL_OUTPUT" | grep -o '[a-f0-9-]\{36\}' | head -1)
    
    if [ -z "$TUNNEL_ID" ]; then
        print_error "無法獲取 Tunnel ID"
        exit 1
    fi
    
    print_success "Tunnel 創建成功: $TUNNEL_ID"
}

# 配置 Cloudflare Tunnel
configure_tunnel() {
    print_step "配置 Cloudflare Tunnel..."
    
    # 創建配置目錄
    mkdir -p "$HOME/.cloudflared"
    
    # 生成隨機子域名
    SUBDOMAIN="app-$(date +%s | tail -c 6)"
    TUNNEL_DOMAIN="${SUBDOMAIN}.$(cloudflared tunnel list | grep $TUNNEL_ID | awk '{print $3}' | head -1 || echo 'your-domain.com')"
    
    # 如果無法自動獲取域名，使用 trycloudflare
    if [[ "$TUNNEL_DOMAIN" == *"your-domain.com"* ]]; then
        print_warning "使用臨時域名模式"
        USE_QUICK_TUNNEL=true
    else
        USE_QUICK_TUNNEL=false
        
        # 創建配置文件
        cat > "$CONFIG_FILE" << EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: $TUNNEL_DOMAIN
    service: http://localhost:80
  - service: http_status:404
EOF
        
        print_success "配置文件已創建: $CONFIG_FILE"
    fi
}

# 啟動 Docker 服務
start_docker_services() {
    print_step "啟動 Docker 服務..."
    
    # 檢查 .env 文件
    if [ ! -f ".env" ]; then
        print_warning "創建 .env 文件"
        cp .env.example .env
    fi
    
    # 生成臨時 SSL 證書
    print_status "生成臨時 SSL 證書..."
    mkdir -p nginx/ssl
    if [ ! -f "nginx/ssl/cloudflare.pem" ]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/cloudflare.key \
            -out nginx/ssl/cloudflare.pem \
            -subj "/C=TW/ST=Taiwan/L=Taipei/O=AutoDeploy/CN=localhost" \
            2>/dev/null
        chmod 600 nginx/ssl/cloudflare.key
        chmod 644 nginx/ssl/cloudflare.pem
    fi
    
    # 停止現有服務
    print_status "停止現有服務..."
    docker-compose down 2>/dev/null || true
    
    # 啟動服務
    print_status "構建並啟動服務..."
    docker-compose up --build -d
    
    # 等待服務啟動
    print_status "等待服務啟動..."
    sleep 15
    
    # 檢查服務狀態
    if ! curl -s http://localhost/health | grep -q "healthy"; then
        print_warning "服務可能需要更多時間啟動，繼續等待..."
        sleep 10
    fi
    
    print_success "Docker 服務啟動完成"
}

# 啟動 Cloudflare Tunnel
start_tunnel() {
    print_step "啟動 Cloudflare Tunnel..."
    
    if [ "$USE_QUICK_TUNNEL" = true ]; then
        # 使用快速臨時 tunnel
        print_status "啟動臨時 tunnel..."
        cloudflared tunnel --url http://localhost:80 > tunnel.log 2>&1 &
        TUNNEL_PID=$!
        
        # 等待 tunnel 啟動並獲取 URL
        sleep 10
        TUNNEL_URL=$(grep -o 'https://.*\.trycloudflare\.com' tunnel.log | head -1)
        
        if [ -z "$TUNNEL_URL" ]; then
            print_error "無法獲取 tunnel URL"
            cat tunnel.log
            exit 1
        fi
    else
        # 使用配置的 tunnel
        print_status "啟動配置的 tunnel..."
        cloudflared tunnel run $TUNNEL_NAME > tunnel.log 2>&1 &
        TUNNEL_PID=$!
        
        sleep 5
        TUNNEL_URL="https://$TUNNEL_DOMAIN"
    fi
    
    # 保存 PID 以便後續清理
    echo $TUNNEL_PID > tunnel.pid
    
    print_success "Tunnel 啟動成功"
}

# 測試連接
test_connection() {
    print_step "測試連接..."
    
    print_status "等待 tunnel 完全啟動..."
    sleep 10
    
    # 測試本地連接
    if curl -s http://localhost/health | grep -q "healthy"; then
        print_success "本地連接正常"
    else
        print_warning "本地連接異常，但繼續測試外部連接"
    fi
    
    # 測試外部連接
    print_status "測試外部連接: $TUNNEL_URL"
    
    local retry_count=0
    local max_retries=6
    
    while [ $retry_count -lt $max_retries ]; do
        if curl -s "$TUNNEL_URL/health" | grep -q "healthy"; then
            print_success "外部連接測試成功"
            return 0
        fi
        
        retry_count=$((retry_count + 1))
        print_status "重試 $retry_count/$max_retries..."
        sleep 10
    done
    
    print_warning "外部連接測試失敗，但服務可能仍在啟動中"
}

# 顯示結果
show_results() {
    print_success "🎉 部署完成！"
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                        🌍 訪問資訊                           ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}📱 對外網址 (可直接分享):${NC}"
    echo -e "${YELLOW}   $TUNNEL_URL${NC}"
    echo ""
    echo -e "${CYAN}🔗 測試連結:${NC}"
    echo -e "   前端應用: ${YELLOW}$TUNNEL_URL${NC}"
    echo -e "   API 端點: ${YELLOW}$TUNNEL_URL/api${NC}"
    echo -e "   健康檢查: ${YELLOW}$TUNNEL_URL/health${NC}"
    echo ""
    echo -e "${CYAN}📱 用戶端連結:${NC}"
    echo -e "   主板模式: ${YELLOW}$TUNNEL_URL/host${NC}"
    echo -e "   用戶模式: ${YELLOW}$TUNNEL_URL/user${NC}"
    echo -e "   房間模式: ${YELLOW}$TUNNEL_URL/room${NC}"
    echo ""
    echo -e "${CYAN}🛠️  本地管理:${NC}"
    echo -e "   本地訪問: ${YELLOW}http://localhost${NC}"
    echo -e "   Docker 狀態: ${YELLOW}docker-compose ps${NC}"
    echo -e "   查看日誌: ${YELLOW}docker-compose logs -f${NC}"
    echo ""
    echo -e "${CYAN}🚨 停止服務:${NC}"
    echo -e "   停止全部: ${YELLOW}./stop-services.sh${NC}"
    echo -e "   或手動: ${YELLOW}docker-compose down && kill \$(cat tunnel.pid)${NC}"
    echo ""
    echo -e "${GREEN}✨ 網址已複製到剪貼簿 (如果支援)${NC}"
    
    # 嘗試複製到剪貼簿
    if command -v pbcopy &> /dev/null; then
        echo "$TUNNEL_URL" | pbcopy
        print_success "網址已複製到 macOS 剪貼簿"
    elif command -v xclip &> /dev/null; then
        echo "$TUNNEL_URL" | xclip -selection clipboard
        print_success "網址已複製到 Linux 剪貼簿"
    fi
}

# 創建停止服務腳本
create_stop_script() {
    cat > stop-services.sh << 'EOF'
#!/bin/bash

echo "🛑 停止所有服務..."

# 停止 Docker 服務
if [ -f "docker-compose.yml" ]; then
    docker-compose down
    echo "✅ Docker 服務已停止"
fi

# 停止 Cloudflare Tunnel
if [ -f "tunnel.pid" ]; then
    TUNNEL_PID=$(cat tunnel.pid)
    if kill -0 $TUNNEL_PID 2>/dev/null; then
        kill $TUNNEL_PID
        echo "✅ Cloudflare Tunnel 已停止"
    fi
    rm -f tunnel.pid
fi

# 清理日誌文件
rm -f tunnel.log

echo "🎉 所有服務已停止"
EOF
    
    chmod +x stop-services.sh
}

# 主函數
main() {
    print_header
    
    # 捕獲 Ctrl+C 信號
    trap 'print_error "部署被中斷"; exit 1' INT
    
    check_dependencies
    check_cloudflare_auth
    create_tunnel
    configure_tunnel
    start_docker_services
    start_tunnel
    test_connection
    create_stop_script
    show_results
    
    print_success "🚀 一鍵部署完成！"
    print_status "服務將繼續在背景運行..."
    print_status "使用 ./stop-services.sh 停止所有服務"
}

# 執行主函數
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi