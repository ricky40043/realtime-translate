# Cloudflare 配置指南

## 🌐 域名設置步驟

### 1. DNS 記錄配置

在 Cloudflare DNS 設置中添加以下記錄：

```
類型: A
名稱: @ (或你的子域名，如 app)
IPv4 地址: 你的服務器 IP
代理狀態: ✅ 已代理 (橘色雲朵)
TTL: 自動
```

```
類型: A  
名稱: www
IPv4 地址: 你的服務器 IP
代理狀態: ✅ 已代理 (橘色雲朵)
TTL: 自動
```

### 2. SSL/TLS 設置

#### 加密模式
- 前往 **SSL/TLS** → **Overview**
- 設置加密模式為：**Full (strict)**

#### Origin Certificate 生成
1. **SSL/TLS** → **Origin Server**
2. 點擊 **Create Certificate**
3. 設置域名：
   - `your-domain.com`
   - `*.your-domain.com`
4. 有效期：15 年
5. 下載證書並放置到 `nginx/ssl/` 目錄

### 3. 安全設置

#### Always Use HTTPS
- **SSL/TLS** → **Edge Certificates**
- 開啟 **Always Use HTTPS**

#### HSTS
- **SSL/TLS** → **Edge Certificates**
- 開啟 **HTTP Strict Transport Security (HSTS)**
- 設置：
  - Status: ✅ Enable HSTS
  - Max Age Header: 6 months
  - Include Subdomains: ✅
  - Preload: ✅

### 4. 性能優化

#### 緩存設置
- **Caching** → **Configuration**
- Caching Level: **Standard**

#### Auto Minify
- **Speed** → **Optimization**
- Auto Minify: 開啟 JavaScript, CSS, HTML

#### Brotli Compression
- **Speed** → **Optimization**
- 開啟 **Brotli**

### 5. 頁面規則 (Page Rules)

設置以下頁面規則來優化性能：

```
Rule 1: your-domain.com/api/*
- Cache Level: Bypass
- Always Online: Off

Rule 2: your-domain.com/ws
- Cache Level: Bypass
- Always Online: Off

Rule 3: your-domain.com/*
- Cache Level: Standard
- Browser Cache TTL: 4 hours
- Always Online: On
```

## 🚀 部署流程

### 1. 更新域名配置

在 `nginx/nginx.conf` 中將 `your-domain.com` 替換為你的實際域名：

```bash
sed -i 's/your-domain.com/actual-domain.com/g' nginx/nginx.conf
```

### 2. 設置 SSL 證書

將 Cloudflare Origin Certificate 放置到正確位置：

```bash
# 複製證書文件到 nginx/ssl/ 目錄
cp /path/to/your/certificate.pem nginx/ssl/cloudflare.pem
cp /path/to/your/private.key nginx/ssl/cloudflare.key

# 設置正確權限
chmod 644 nginx/ssl/cloudflare.pem
chmod 600 nginx/ssl/cloudflare.key
```

### 3. 啟動服務

```bash
# 構建並啟動所有服務
docker-compose up --build -d

# 檢查服務狀態
docker-compose ps

# 查看 nginx 日誌
docker-compose logs nginx

# 測試配置
curl -I http://your-domain.com/health
```

### 4. 驗證設置

- ✅ HTTP 自動重定向到 HTTPS
- ✅ SSL 證書有效
- ✅ 前端服務正常訪問
- ✅ API 端點 `/api/*` 正常
- ✅ WebSocket `/ws` 連接正常

## 🔧 故障排除

### 常見問題

1. **SSL 錯誤**
   - 檢查證書文件路徑和權限
   - 確認 Cloudflare 加密模式為 Full (strict)

2. **API 無法訪問**
   - 檢查後端服務是否正常運行
   - 驗證 nginx 上游配置

3. **WebSocket 連接失敗**
   - 確認 WebSocket 代理配置
   - 檢查超時設置

### 日誌檢查

```bash
# 檢查所有服務日誌
docker-compose logs

# 檢查特定服務
docker-compose logs nginx
docker-compose logs backend
docker-compose logs frontend
```

## 📈 監控建議

1. 設置 Cloudflare Analytics
2. 配置 Uptime 監控
3. 啟用 Security Events 通知
4. 設置 Rate Limiting 規則

## 🛡️ 安全建議

1. 定期更新 SSL 證書
2. 啟用 Cloudflare WAF
3. 配置 DDoS 保護
4. 設置適當的 Rate Limiting
5. 使用 Cloudflare Access 保護敏感端點