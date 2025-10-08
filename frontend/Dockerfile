FROM node:22-bookworm-slim

WORKDIR /app

# 只複製 package.json（避免使用宿主機生成的 package-lock.json 造成可選依賴平台不相容）
COPY package.json ./

# 環境變數：禁用 Rollup 原生模組，使用 JS 實作，避免可選依賴在不同架構下拉取失敗
ENV ROLLUP_DISABLE_NATIVE=1
ENV CHOKIDAR_USEPOLLING=true

# 安裝依賴（使用 npm install 以繞過 npm ci 在 optional deps 上的已知問題）
RUN npm install

# 複製所有檔案
COPY . .

# 暴露端口
EXPOSE 5173

# 開發模式啟動，綁定到所有網路介面
CMD ["npm", "run", "dev"]