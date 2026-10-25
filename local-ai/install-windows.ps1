# 雙向翻譯機：Windows 一鍵安裝（本機模型版）
# 會安裝：Docker Desktop、Ollama、Python，並下載語音辨識和翻譯模型。
# 第一次大約要下載 10–20 GB，請接電源、用穩定的網路。
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
function Say($msg) { Write-Host "`n▶ $msg" -ForegroundColor Magenta }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

$ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$hasNvidia = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
Say "這台電腦：記憶體 $ramGb GB，NVIDIA 顯卡：$(if ($hasNvidia) { '有' } else { '沒有' })"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  Write-Host "找不到 winget。請先到 Microsoft Store 安裝「應用程式安裝程式 (App Installer)」再執行一次。"
  exit 1
}

Say "安裝 Docker Desktop、Ollama、Python（可能會跳出系統權限視窗，請按「是」）"
foreach ($id in "Docker.DockerDesktop", "Ollama.Ollama", "Python.Python.3.12") {
  winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent
  if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { Write-Host "（$id 可能已經裝過，繼續）" }
}
Refresh-Path

# ---------- 選模型 ----------
if ($hasNvidia) { $sttModels = "large-v3-turbo,large-v3,small" } else { $sttModels = "small,large-v3-turbo" }
# 翻譯模型：有 NVIDIA 顯卡用 9B（品質較好）；只有 CPU 用小模型才跟得上講話速度
if ($hasNvidia -and $ramGb -ge 16) { $llmModels = @("qwen3.5:9b", "gemma4:e4b") } else { $llmModels = @("qwen3.5:4b", "gemma4:e2b") }

# ---------- 語音辨識（Whisper） ----------
Say "建立語音辨識環境"
py -3.12 -m venv local-ai\.venv
$py = "local-ai\.venv\Scripts\python.exe"
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -r local-ai\requirements.txt
if ($hasNvidia) {
  Say "安裝 NVIDIA 顯卡加速元件"
  & $py -m pip install -q "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
}
"STT_MODELS=$sttModels" | Out-File -Encoding ascii local-ai\settings.env
Say "下載語音辨識模型：$sttModels（第一次比較久）"
$env:STT_MODELS = $sttModels
& $py local-ai\stt_server.py --download-only

# ---------- 翻譯模型（Ollama） ----------
Say "下載翻譯模型：$($llmModels -join ', ')"
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
  Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe" -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 5
}
foreach ($m in $llmModels) { ollama pull $m }

# ---------- 設定檔 ----------
if (-not (Test-Path .env)) {
  Say "建立設定檔 .env"
  $groq = Read-Host "要不要也能用雲端 Groq（品質最好，需要網路）？有的話貼上 GROQ API Key，沒有直接按 Enter"
  $bytes = New-Object byte[] 32
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
  @"
JWT_SECRET=$secret
STT_PROVIDER=groq
TRANSLATE_PROVIDER=free
GROQ_API_KEY=$groq
LAN_IP=
"@ | Out-File -Encoding ascii .env
}

Say "安裝完成，開始啟動"
& "$PSScriptRoot\start-windows.ps1"
