FROM node:18-alpine

WORKDIR /app

# 複製 package.json 檔案
COPY package*.json ./

# 安裝依賴
RUN npm ci

# 複製所有檔案
COPY . .

# 暴露端口
EXPOSE 5173

# 開發模式啟動
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]