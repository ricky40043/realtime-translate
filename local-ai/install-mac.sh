#!/bin/bash
# 雙向翻譯機：Mac 一鍵安裝（本機模型版）
# 會安裝：Homebrew、Docker Desktop、Ollama、ffmpeg、Python，並下載語音辨識和翻譯模型。
# 第一次大約要下載 10–20 GB，請接電源、用穩定的網路。
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
say() { printf "\n\033[1;35m▶ %s\033[0m\n" "$1"; }

ARCH="$(uname -m)"
RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
say "這台 Mac：$ARCH，記憶體 ${RAM_GB} GB"

# ---------- Homebrew ----------
if ! command -v brew >/dev/null 2>&1; then
  say "安裝 Homebrew（會要求輸入電腦密碼）"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; else eval "$(/usr/local/bin/brew shellenv)"; fi
fi

say "安裝 Ollama、ffmpeg、Python"
brew install ollama ffmpeg python@3.12
if ! command -v docker >/dev/null 2>&1 && [ ! -d /Applications/Docker.app ]; then
  say "安裝 Docker Desktop"
  brew install --cask docker
fi

# ---------- 選模型（依記憶體大小） ----------
if [ "$ARCH" = "arm64" ]; then
  # Apple 晶片用 GPU 跑，turbo 一句不到一秒
  if [ "$RAM_GB" -ge 16 ]; then STT_MODELS="large-v3-turbo,large-v3,small"; else STT_MODELS="large-v3-turbo,small"; fi
  REQ=requirements-mac.txt
else
  # Intel Mac 只能用 CPU：預設小模型才跟得上
  STT_MODELS="small,large-v3-turbo"
  REQ=requirements.txt
fi
# 翻譯模型：Apple 晶片 + 16 GB 以上用 9B（品質較好）；Intel Mac 只有 CPU，用小模型才跟得上講話速度
if [ "$ARCH" = "arm64" ] && [ "$RAM_GB" -ge 16 ]; then LLM_MODELS="qwen3.5:9b gemma4:e4b"; else LLM_MODELS="qwen3.5:4b gemma4:e2b"; fi

# ---------- 語音辨識（Whisper） ----------
say "建立語音辨識環境"
python3.12 -m venv local-ai/.venv
local-ai/.venv/bin/pip install -q --upgrade pip
local-ai/.venv/bin/pip install -q -r "local-ai/$REQ"
echo "STT_MODELS=$STT_MODELS" > local-ai/settings.env
say "下載語音辨識模型：$STT_MODELS（第一次比較久）"
STT_MODELS="$STT_MODELS" local-ai/.venv/bin/python local-ai/stt_server.py --download-only

# ---------- 翻譯模型（Ollama） ----------
say "啟動 Ollama 並下載翻譯模型：$LLM_MODELS"
brew services start ollama >/dev/null
for i in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 1; done
for m in $LLM_MODELS; do ollama pull "$m"; done

# ---------- 設定檔 ----------
if [ ! -f .env ]; then
  say "建立設定檔 .env"
  echo "要不要也能用雲端 Groq（品質最好，需要網路）？有的話貼上 GROQ API Key，沒有直接按 Enter："
  read -r GROQ_KEY
  cat > .env <<ENV
JWT_SECRET=$(openssl rand -hex 32)
STT_PROVIDER=groq
TRANSLATE_PROVIDER=free
GROQ_API_KEY=$GROQ_KEY
LAN_IP=
ENV
fi

chmod +x "$ROOT/啟動翻譯機-Mac.command" local-ai/start-mac.sh
say "安裝完成，開始啟動"
exec local-ai/start-mac.sh
