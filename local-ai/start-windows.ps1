# 雙向翻譯機：Windows 啟動（安裝過一次之後，每次用這個開）
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
function Say($msg) { Write-Host "`n▶ $msg" -ForegroundColor Magenta }
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

# Docker Desktop
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Say "啟動 Docker Desktop（第一次開會要求同意條款）"
  Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  for ($i = 0; $i -lt 120; $i++) { docker info *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 2 }
  docker info *> $null
  if ($LASTEXITCODE -ne 0) { Write-Host "Docker 沒有啟動，請手動打開 Docker Desktop 後再執行一次"; exit 1 }
}

# Ollama（翻譯模型）
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
  Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe" -ErrorAction SilentlyContinue
}

# 這台電腦在區網的 IP（手機連線用）
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.PrefixOrigin -in "Dhcp", "Manual" -and $_.IPAddress -notlike "169.254*" -and $_.InterfaceAlias -notlike "vEthernet*" } |
  Select-Object -First 1).IPAddress
if (-not $lanIp) { $lanIp = "127.0.0.1" }
$envText = Get-Content .env -Raw
if ($envText -match "(?m)^LAN_IP=") { $envText = $envText -replace "(?m)^LAN_IP=.*", "LAN_IP=$lanIp" } else { $envText += "`nLAN_IP=$lanIp`n" }
$envText | Out-File -Encoding ascii .env -NoNewline

# 語音辨識服務
New-Item -ItemType Directory -Force local-ai\logs | Out-Null
try { Invoke-WebRequest http://127.0.0.1:9000/health -UseBasicParsing -TimeoutSec 2 | Out-Null; $sttUp = $true } catch { $sttUp = $false }
if (-not $sttUp) {
  Say "啟動語音辨識（Whisper）"
  Get-Content local-ai\settings.env | ForEach-Object { $k, $v = $_ -split "=", 2; if ($k) { Set-Item "env:$k" $v } }
  # NVIDIA 加速元件的 DLL 在 pip 套件裡，要加進 PATH
  $nv = Get-ChildItem "local-ai\.venv\Lib\site-packages\nvidia\*\bin" -Directory -ErrorAction SilentlyContinue
  if ($nv) { $env:Path = ($nv.FullName -join ";") + ";" + $env:Path }
  Start-Process -WindowStyle Hidden -FilePath "local-ai\.venv\Scripts\python.exe" -ArgumentList "local-ai\stt_server.py" `
    -RedirectStandardOutput local-ai\logs\stt.log -RedirectStandardError local-ai\logs\stt-error.log
}

Say "啟動翻譯機"
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest http://localhost:3100/ -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 2 }
}

# 手機要信任的憑證（Caddy 第一次啟動才會產生）
for ($i = 0; $i -lt 15; $i++) {
  docker compose -f docker-compose.yml -f docker-compose.local.yml cp https:/data/caddy/pki/authorities/local/root.crt "local-ai\手機憑證.crt" *> $null
  if ($LASTEXITCODE -eq 0) { break }
  Start-Sleep 1
}

Start-Process "http://localhost:3100/translator"
Write-Host @"

✅ 翻譯機已啟動
   這台電腦：http://localhost:3100/translator
   手機（同一個 Wi-Fi）：https://${lanIp}:3443/translator
     第一次用手機要先安裝並信任「local-ai\手機憑證.crt」，步驟見 local-ai\README.md
     Windows 防火牆跳出詢問時請按「允許」
   設定 → 語音辨識 / 翻譯模型 選「本機」就不需要網路。
   關閉：執行「停止翻譯機-Windows.bat」
"@
