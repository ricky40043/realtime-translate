# 多階段建構：第一階段 - 建構
FROM node:22-bookworm-slim AS builder

WORKDIR /app

# 只複製 package.json（避免使用宿主機生成的 package-lock.json 造成可選依賴平台不相容）
COPY package.json ./

# 環境變數：禁用 Rollup 原生模組，使用 JS 實作，避免可選依賴在不同架構下拉取失敗
ENV ROLLUP_DISABLE_NATIVE=1

# 安裝依賴（使用 npm install 以繞過 npm ci 在 optional deps 上的已知問題）
RUN npm install

# 複製所有檔案
COPY . .

# 建構生產版本
RUN npm run build

# 第二階段 - 生產環境
FROM nginx:alpine

# 刪除 nginx 默認文件
RUN rm -rf /usr/share/nginx/html/*

# 複製建構結果到 nginx
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# 複製 nginx 配置
COPY nginx.conf /etc/nginx/nginx.conf

# 暴露端口
EXPOSE 80

# 啟動 nginx
CMD ["nginx", "-g", "daemon off;"]