#!/bin/bash
# 雙向翻譯機：Mac 啟動（安裝過一次之後，每次用這個開）
set -e
cd "$(dirname "$0")/.."
say() { printf "\n\033[1;35m▶ %s\033[0m\n" "$1"; }
if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi

# Docker Desktop
if ! docker info >/dev/null 2>&1; then
  say "啟動 Docker Desktop（第一次開會要求同意條款）"
  open -a Docker
  for i in $(seq 1 120); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || { echo "Docker 沒有啟動，請手動打開 Docker Desktop 後再執行一次"; exit 1; }
fi

# Ollama（翻譯模型）
brew services start ollama >/dev/null 2>&1 || true

# 這台電腦在區網的 IP（手機連線用）
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"
if grep -q '^LAN_IP=' .env; then sed -i '' "s/^LAN_IP=.*/LAN_IP=$LAN_IP/" .env; else echo "LAN_IP=$LAN_IP" >> .env; fi

# 語音辨識服務
mkdir -p local-ai/logs
if ! curl -sf http://127.0.0.1:9000/health >/dev/null; then
  say "啟動語音辨識（Whisper）"
  set -a; . local-ai/settings.env; set +a
  nohup local-ai/.venv/bin/python local-ai/stt_server.py > local-ai/logs/stt.log 2>&1 &
fi

say "啟動翻譯機"
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
for i in $(seq 1 60); do curl -sf http://localhost:3100/ >/dev/null && break; sleep 2; done

# 手機要信任的憑證（Caddy 第一次啟動才會產生）
for i in $(seq 1 15); do
  docker compose -f docker-compose.yml -f docker-compose.local.yml cp \
    https:/data/caddy/pki/authorities/local/root.crt "local-ai/手機憑證.crt" >/dev/null 2>&1 && break
  sleep 1
done

open "http://localhost:3100/translator"
cat <<MSG

✅ 翻譯機已啟動
   這台電腦：http://localhost:3100/translator
   手機（同一個 Wi-Fi）：https://$LAN_IP:3443/translator
     第一次用手機要先安裝並信任「local-ai/手機憑證.crt」，步驟見 local-ai/README.md
   設定 → 語音辨識 / 翻譯模型 選「本機」就不需要網路。
   關閉：執行「停止翻譯機-Mac.command」
MSG
