"""
本機模型：不用網路也能翻譯（展場網路差、或不想用雲端額度時）。

- 語音辨識：local-ai/stt_server.py（Whisper，OpenAI 相容的 /v1/audio/transcriptions）
- 翻譯：Ollama（/api/chat）

兩個網址都沒設定、或連不到時，設定畫面就不會列出本機模型。
"""

import os
import time
from typing import Dict, List, Optional

import httpx

LOCAL_STT_URL = os.getenv("LOCAL_STT_URL", "").rstrip("/")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "").rstrip("/")

# 實測：靜音約 0.7、正常說話約 0.02（和 Groq 那邊一樣的判斷）
NO_SPEECH_THRESHOLD = 0.5
MAX_COMPRESSION_RATIO = 2.4

# 不是拿來對話的模型（向量、嵌入），不列在翻譯模型裡
_NON_CHAT = ("embed", "bge", "minilm", "rerank")

_client: Optional[httpx.AsyncClient] = None
_models_cache: Dict[str, tuple] = {}


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        # 本機模型第一次載入可能要幾十秒
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=3.0))
    return _client


async def _cached(key: str, loader) -> List[str]:
    hit = _models_cache.get(key)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    try:
        value = await loader()
    except Exception as e:
        print(f"⚠️ [LocalAI] 讀取 {key} 模型清單失敗: {e}")
        value = []
    _models_cache[key] = (time.time(), value)
    return value


async def list_stt_models() -> List[str]:
    if not LOCAL_STT_URL:
        return []

    async def load():
        resp = await _http().get(f"{LOCAL_STT_URL}/v1/models", timeout=3.0)
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]

    return await _cached("stt", load)


async def list_llm_models() -> List[str]:
    if not LOCAL_LLM_URL:
        return []

    async def load():
        resp = await _http().get(f"{LOCAL_LLM_URL}/api/tags", timeout=3.0)
        resp.raise_for_status()
        names = [m["name"] for m in resp.json().get("models", [])]
        return sorted(n for n in names if not any(k in n.lower() for k in _NON_CHAT))

    return await _cached("llm", load)


async def transcribe(audio_data: bytes, content_type: str, model: str) -> Dict:
    """回傳格式和 groq_stt 一樣：text / language / no_speech_prob"""
    suffix = ".mp3" if "mpeg" in content_type or "mp3" in content_type else ".wav"
    try:
        resp = await _http().post(
            f"{LOCAL_STT_URL}/v1/audio/transcriptions",
            files={"file": (f"audio{suffix}", audio_data, content_type)},
            data={"model": model, "response_format": "verbose_json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"❌ [LocalAI] 本機語音辨識失敗: {e}")
        return {"text": "", "language": "", "no_speech_prob": 0.0, "error": str(e)}

    text = data.get("text", "")
    segments = data.get("segments") or []
    no_speech = max((s.get("no_speech_prob", 0.0) for s in segments), default=0.0)
    kept = [s for s in segments
            if s.get("no_speech_prob", 0.0) < NO_SPEECH_THRESHOLD
            and s.get("compression_ratio", 0.0) < MAX_COMPRESSION_RATIO]
    if segments and len(kept) != len(segments):
        text = "".join(s.get("text", "") for s in kept)
    return {"text": text, "language": data.get("language", ""), "no_speech_prob": no_speech, "confidence": 0.9}


_llm_busy = 0  # 正在跑的本機翻譯數


async def translate(text: str, target_name: str, model: str, skip_if_busy: bool = False) -> Dict:
    """skip_if_busy：講話中的即時預覽在模型忙的時候先不翻（沒顯卡的電腦一句要好幾秒，讓定稿先用）"""
    global _llm_busy
    if skip_if_busy and _llm_busy:
        return {"text": "", "skipped": True}
    _llm_busy += 1
    try:
        resp = await _http().post(
            f"{LOCAL_LLM_URL}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,  # Qwen 等會「先想再答」的模型：即時翻譯不需要，關掉快很多
                "keep_alive": "2h",
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": (
                        f"You are a real-time interpreter. Translate the user's message into {target_name}. "
                        "The message is a speech-recognition transcript and may contain mixed languages or small errors; "
                        "translate the intended meaning naturally. If it is already in the target language, return it "
                        "unchanged (but convert Chinese script to the target variant). Output only the translation, "
                        "with no quotes, notes or explanations."
                    )},
                    {"role": "user", "content": text},
                ],
            },
        )
        resp.raise_for_status()
        translated = (resp.json().get("message", {}).get("content") or "").strip()
        return {"text": translated, "provider": f"ollama:{model}"}
    except Exception as e:
        print(f"❌ [LocalAI] 本機翻譯失敗: {e}")
        return {"text": "", "error": str(e)}
    finally:
        _llm_busy -= 1
