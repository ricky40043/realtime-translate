#!/bin/bash
# 雙向翻譯機：Mac 停止
cd "$(dirname "$0")/.."
docker compose -f docker-compose.yml -f docker-compose.local.yml stop
pkill -f "local-ai/stt_server.py" || true
echo "✅ 已停止（Ollama 會留著，不佔資源；要關可以執行 brew services stop ollama）"
