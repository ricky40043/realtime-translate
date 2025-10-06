#!/bin/bash

# 部署腳本 - 多語言聊天應用

set -e

echo "🚀 開始部署多語言聊天應用..."

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函數：打印彩色訊息
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

# 檢查必需文件
check_requirements() {
    print_status "檢查部署環境..."
    
    # 檢查 Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安裝，請先安裝 Docker"
        exit 1
    fi
    
    # 檢查 Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose 未安裝，請先安裝 Docker Compose"
        exit 1
    fi
    
    # 檢查 .env 文件
    if [ ! -f ".env" ]; then
        print_warning ".env 文件不存在，將使用 .env.example"
        cp .env.example .env
        print_warning "請編輯 .env 文件設置正確的環境變數"
    fi
    
    print_success "環境檢查完成"
}

# 設置域名
setup_domain() {
    read -p "請輸入你的域名 (例如: example.com): " DOMAIN
    
    if [ -z "$DOMAIN" ]; then
        print_warning "未輸入域名，將使用 localhost"
        DOMAIN="localhost"
    fi
    
    print_status "設置域名: $DOMAIN"
    
    # 更新 nginx 配置中的域名
    if [ -f "nginx/nginx.conf" ]; then
        sed -i.backup "s/your-domain.com/$DOMAIN/g" nginx/nginx.conf
        print_success "已更新 nginx 配置中的域名"
    fi
}

# 檢查 SSL 證書
check_ssl() {
    print_status "檢查 SSL 證書..."
    
    if [ ! -f "nginx/ssl/cloudflare.pem" ] || [ ! -f "nginx/ssl/cloudflare.key" ]; then
        print_warning "未找到 SSL 證書文件"
        read -p "是否要生成臨時自簽證書用於測試? (y/n): " GENERATE_CERT
        
        if [ "$GENERATE_CERT" = "y" ] || [ "$GENERATE_CERT" = "Y" ]; then
            generate_self_signed_cert
        else
            print_warning "請將 Cloudflare Origin Certificate 放置到 nginx/ssl/ 目錄"
            print_warning "參考 nginx/ssl/README.md 獲取詳細說明"
        fi
    else
        print_success "SSL 證書文件已存在"
    fi
}

# 生成自簽證書
generate_self_signed_cert() {
    print_status "生成自簽 SSL 證書..."
    
    mkdir -p nginx/ssl
    
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/ssl/cloudflare.key \
        -out nginx/ssl/cloudflare.pem \
        -subj "/C=TW/ST=Taiwan/L=Taipei/O=TestCompany/CN=$DOMAIN" \
        2>/dev/null
    
    chmod 600 nginx/ssl/cloudflare.key
    chmod 644 nginx/ssl/cloudflare.pem
    
    print_success "自簽證書生成完成"
    print_warning "這是測試證書，生產環境請使用 Cloudflare Origin Certificate"
}

# 構建和啟動服務
deploy_services() {
    print_status "停止現有服務..."
    docker-compose down 2>/dev/null || true
    
    print_status "構建服務鏡像..."
    docker-compose build --no-cache
    
    print_status "啟動服務..."
    docker-compose up -d
    
    # 等待服務啟動
    print_status "等待服務啟動..."
    sleep 10
}

# 檢查服務狀態
check_services() {
    print_status "檢查服務狀態..."
    
    # 檢查容器狀態
    if ! docker-compose ps | grep -q "Up"; then
        print_error "部分服務啟動失敗"
        docker-compose ps
        docker-compose logs
        exit 1
    fi
    
    # 檢查健康狀態
    print_status "測試服務連接..."
    
    # 測試 HTTP
    if curl -s -o /dev/null -w "%{http_code}" http://localhost/health | grep -q "200"; then
        print_success "HTTP 服務正常"
    else
        print_warning "HTTP 服務可能未正常啟動"
    fi
    
    # 測試 HTTPS (如果有證書)
    if [ -f "nginx/ssl/cloudflare.pem" ]; then
        if curl -k -s -o /dev/null -w "%{http_code}" https://localhost/health | grep -q "200"; then
            print_success "HTTPS 服務正常"
        else
            print_warning "HTTPS 服務可能未正常啟動"
        fi
    fi
}

# 顯示部署結果
show_results() {
    print_success "🎉 部署完成！"
    echo ""
    echo "📋 服務信息："
    echo "  前端: http://localhost"
    echo "  API:  http://localhost/api"
    echo "  WebSocket: ws://localhost/ws"
    
    if [ -f "nginx/ssl/cloudflare.pem" ]; then
        echo "  HTTPS: https://localhost"
    fi
    
    echo ""
    echo "🔧 管理命令："
    echo "  查看狀態: docker-compose ps"
    echo "  查看日誌: docker-compose logs"
    echo "  停止服務: docker-compose down"
    echo "  重啟服務: docker-compose restart"
    
    echo ""
    echo "📚 下一步："
    echo "  1. 設置你的域名 DNS 記錄指向此服務器"
    echo "  2. 在 Cloudflare 配置 SSL/TLS 設置"
    echo "  3. 參考 cloudflare-setup.md 完成 Cloudflare 配置"
}

# 主執行流程
main() {
    echo "🌍 多語言聊天應用部署腳本"
    echo "================================"
    
    check_requirements
    setup_domain
    check_ssl
    deploy_services
    check_services
    show_results
}

# 如果腳本被直接執行
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi