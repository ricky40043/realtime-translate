
# 行動版白屏排查清單

目的：逐步檢查「打包版在手機白屏或沒資料」問題，並在每步得到結論與修正方式。

---

## 0. 基本資訊
- 目標頁面：`https://<域名>/user/<id>`
- 伺服器：Nginx 或容器反代
- 前端：Vite + Vue（已打包）
- 後端 API：`/api/*` 或環境變數指定

---

## 1) 確認頁面是否載入打包 JS/CSS
```bash
curl -s https://<域名>/user/<id> | grep -Eo '/assets/[^"]+\.(js|css)' | sort -u
```
**期望**：列出至少一個 `.js`（可能還有 `.css`）。  
**若無**：仍在用開發腳本 `/src/main.ts`。請確認部署的是 `dist/index.html`，`<script type="module" src="assets/*.js">`。

---

## 2) 檢查靜態資源 MIME 與內容
```bash
curl -I https://<域名>/assets/<檔名>.js
curl -s https://<域名>/assets/<檔名>.js | head -n 3
```
**期望**：`content-type: application/javascript`，內容是 JS。  
**異常**：
- `text/html` 或開頭 `<!doctype html>` → 被 SPA fallback。修 Nginx。  
- `X-Content-Type-Options: nosniff` 且型別錯 → 修正 MIME。  
- `content-encoding` 同時 `br` 和 `gzip` → 取消雙重壓縮。

---

## 3) 檢查 CSP 與 CORS
```bash
curl -I https://<域名>/user/<id> | grep -i 'content-security-policy\|access-control-allow-origin\|access-control-allow-credentials'
```
- 若有 `Content-Security-Policy`：需允許同網域 `script-src`、`connect-src`。  
- 若使用 Cookie：  
  - 後端回 `Access-Control-Allow-Origin: https://<域名>` 與 `Access-Control-Allow-Credentials: true`  
  - Cookie 必須 `SameSite=None; Secure`

---

## 4) API 是否被 SPA fallback 或跨域失敗
```bash
curl -i https://<域名>/api/health
curl -i https://<域名>/api/<實際端點>
```
**期望**：`application/json`。  
**若回 HTML**：API 被前端路由吃掉，修 Nginx。  
**若 401/403 或 CORS 錯**：調整 CORS 與 Cookie 設定。

---

## 5) 打包 JS 內的 API/WS URL
```bash
for p in $(curl -s https://<域名>/user/<id> | grep -Eo '/assets/[^"]+\.js' | sort -u); do
  echo "== $p ==";
  curl -s https://<域名>$p | strings | grep -E 'https?://|wss?://|/api' | head -n 20
done
```
**期望**：URL 是相對 `/api` 或 `https://<域名>`，且 WS 用 `wss://`。  
**若看到 `http://localhost:*` 或 `ws://`**：修改 `.env.production`，重建。

---

## 6) 清掉 Service Worker / PWA 快取
- Safari/Chrome DevTools → Application → Service Workers → Unregister  
- 或打包時先移除註冊程式碼測試。

---

## 7) iOS 相容性保險
加入 legacy plugin 降低不相容風險：
```bash
npm i -D @vitejs/plugin-legacy
```
```ts
// vite.config.ts
import legacy from '@vitejs/plugin-legacy'
export default defineConfig({
  plugins: [vue(), legacy({ targets: ['defaults', 'iOS >= 12', 'Safari >= 12'] })],
  build: { target: 'es2018' }
})
```

---

## Nginx 參考設定

### 靜態與 API 分流
```nginx
server {
  include       mime.types;
  default_type  application/octet-stream;
  root /path/to/dist;

  # 先匹配 API
  location /api/ {
    proxy_pass http://backend:8888;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
  }

  # 靜態資源直出
  location /assets/ {
    try_files $uri =404;
  }

  # 其他路由 fallback
  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

### 避免雙重壓縮
```nginx
gzip off;
```

### CORS 與 Cookie
- 後端 Set-Cookie：`SameSite=None; Secure; Path=/; HttpOnly`  
- Header：
  ```
  Access-Control-Allow-Origin: https://<域名>
  Access-Control-Allow-Credentials: true
  ```
- 前端：
  ```ts
  fetch('/api/xxx', { credentials: 'include' })
  ```

---

## 最終驗收
- `/user/<id>` HTML 含 `/assets/*.js`。  
- JS 正確 MIME。  
- API 正常回 JSON。  
- 打包內無 `localhost` 或 `ws://`。  
- 清除 SW 後手機可正常載入。  
- 若需登入，CORS/Cookie 正確。  
- 如仍白屏，用行動裝置遠端偵錯查看 Console。
