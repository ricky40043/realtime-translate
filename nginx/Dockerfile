FROM nginx:alpine

# 複製 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 創建 SSL 證書目錄
RUN mkdir -p /etc/ssl/certs /etc/ssl/private

# 設置正確的權限
RUN chmod 755 /etc/ssl/certs /etc/ssl/private

# 健康檢查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]