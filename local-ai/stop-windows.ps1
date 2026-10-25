# 雙向翻譯機：Windows 停止
Set-Location (Split-Path -Parent $PSScriptRoot)
docker compose -f docker-compose.yml -f docker-compose.local.yml stop
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*stt_server.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "✅ 已停止（Ollama 會留在右下角，不佔資源）"
