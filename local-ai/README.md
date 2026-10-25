# 雙向翻譯機：在自己的電腦上跑（本機模型、不需要網路）

在展場網路很差，或不想用雲端額度時，可以把語音辨識和翻譯都放在自己的電腦上跑。
設定畫面可以隨時切換「雲端 Groq」或「本機」模型。

## 一鍵安裝

| 電腦 | 安裝 | 之後每次開啟 | 關閉 |
|---|---|---|---|
| Mac | 雙擊 `一鍵安裝-Mac.command` | `啟動翻譯機-Mac.command` | `停止翻譯機-Mac.command` |
| Windows | 雙擊 `一鍵安裝-Windows.bat` | `啟動翻譯機-Windows.bat` | `停止翻譯機-Windows.bat` |

- 第一次安裝會下載約 10–20 GB（Docker、模型），請接電源、用穩定的網路，大約 20–60 分鐘。
- 安裝完成後，瀏覽器會自動打開 `http://localhost:3100/translator`。
- Mac 雙擊時如果出現「無法打開，因為來自未識別的開發者」：在檔案上按右鍵 →「打開」→「打開」。
- Docker Desktop 第一次開啟要同意使用條款；Windows 可能要求重新開機一次，重開後再執行一次安裝即可。

## 會裝哪些模型

安裝程式依電腦自動選擇：

| 電腦 | 語音辨識（Whisper） | 翻譯（Ollama） |
|---|---|---|
| Apple 晶片 Mac（M1 以後），16 GB 以上 | large-v3-turbo（預設）、large-v3、small | qwen3.5:9b、gemma4:e4b |
| 有 NVIDIA 顯卡的 Windows | large-v3-turbo（預設）、large-v3、small | qwen3.5:9b、gemma4:e4b |
| 只有 CPU（Intel Mac、一般筆電） | small（預設）、large-v3-turbo | qwen3.5:4b、gemma4:e2b |

設定畫面會列出這台電腦上所有可用的模型。想多裝翻譯模型，例如更強但更慢的 `qwen3.5:27b`：
在終端機執行 `ollama pull qwen3.5:27b`，重新整理頁面就會出現在選單裡。

### 速度參考（實測）

只有 CPU（Intel Core Ultra 9 筆電級處理器、沒有顯卡）：

| 模型 | 一句話 |
|---|---|
| Whisper small | 約 1.5–2 秒 |
| Whisper large-v3-turbo | 約 6–7 秒 |
| qwen3.5:9b 翻譯 | 單獨約 2.5 秒；和語音辨識同時跑時會慢到 5–20 秒 |

所以只有 CPU 的電腦預設用 small + 4B 翻譯模型。Apple 晶片 Mac 或 NVIDIA 顯卡會快很多
（turbo 一句通常不到 1 秒），可以用較大的模型。

## 手機怎麼連

麥克風只能在 **HTTPS** 或 **localhost** 網址使用：

- **在這台電腦上用**（筆電 + 外接麥克風）：直接用 `http://localhost:3100/translator`，不用任何設定。
- **用手機或平板連這台電腦**：手機和電腦連同一個 Wi-Fi（或手機開熱點給電腦），
  打開啟動時顯示的 `https://<電腦 IP>:3443/translator`。
  第一次要讓手機信任這台電腦的憑證（只要做一次）：

### iPhone / iPad 信任憑證

1. 把 `local-ai/手機憑證.crt` 傳到手機（AirDrop 最快，或寄 email 給自己用「郵件」App 打開）。
2. 手機跳出「已下載描述檔」→ 到「設定」→「一般」→「VPN 與裝置管理」→ 點剛下載的描述檔 →「安裝」。
3. 「設定」→「一般」→「關於本機」→ 最下面「憑證信任設定」→ 打開「Caddy Local Authority」。
4. 用 Safari 打開 `https://<電腦 IP>:3443/translator`。

### Android 信任憑證

「設定」→「安全性」→「加密與憑證」→「安裝憑證」→「CA 憑證」→ 選 `手機憑證.crt`。

> 電腦換了 Wi-Fi，IP 會變：重新執行「啟動翻譯機」就會更新，網址看啟動時顯示的。
> 憑證不用重裝（同一台電腦一直有效）。

## 沒有網路時

- 設定 →「語音辨識」和「翻譯模型」都選「本機」。
- 雲端 Groq 選項在沒網路時會失敗；本機模型完全不需要網路。
- 安裝時沒有填 Groq API Key 的話，只會有本機模型可選。

## 疑難排解

- **設定裡看不到本機模型**：語音辨識服務或 Ollama 沒開。重新執行「啟動翻譯機」。
  語音辨識的紀錄在 `local-ai/logs/stt.log`。
- **第一句要等很久**：模型第一次載入要 10–30 秒，之後就快了。
- **翻譯很慢**：在設定換小一點的模型（small、4B），或改用雲端 Groq。
