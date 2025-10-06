# SSL 證書配置

## Cloudflare Origin Certificate 設置

1. 登入 Cloudflare Dashboard
2. 選擇你的域名
3. 前往 **SSL/TLS** → **Origin Server**
4. 點擊 **Create Certificate**
5. 選擇 **Let Cloudflare generate a private key and a CSR**
6. 設置域名：
   - `your-domain.com`
   - `*.your-domain.com`
7. 選擇有效期（建議 15 年）
8. 點擊 **Create**

## 證書文件放置

將生成的證書文件放置在此目錄：

```
nginx/ssl/
├── cloudflare.pem    # Origin Certificate (公鑰)
└── cloudflare.key    # Private Key (私鑰)
```

## 臨時自簽證書（測試用）

如果需要臨時測試，可以使用以下命令生成自簽證書：

```bash
# 在 nginx/ssl 目錄中執行
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout cloudflare.key \
    -out cloudflare.pem \
    -subj "/C=TW/ST=Taiwan/L=Taipei/O=YourCompany/CN=your-domain.com"
```

## 權限設置

確保證書文件權限正確：
```bash
chmod 600 nginx/ssl/cloudflare.key
chmod 644 nginx/ssl/cloudflare.pem
```

## 注意事項

- **不要**將真實的私鑰提交到版本控制
- 在生產環境中使用 Cloudflare Origin Certificate
- 確保 Cloudflare SSL 模式設置為 **Full (strict)**