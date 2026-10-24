"""
Groq 剩餘額度：每次呼叫 Groq 時，從回應標頭記下「今天還能呼叫幾次」，
翻譯機畫面右上角顯示用，不需要另外打 API。
"""

import asyncio
import io
import os
import struct
import time
import wave
from typing import Dict, Optional

import httpx

# 定稿用的模型：這兩個用完翻譯機就停了，所以畫面上顯示這兩個
SPEECH_MODEL = "whisper-large-v3"
TRANSLATE_MODEL = os.getenv("GROQ_TRANSLATE_MODEL", "openai/gpt-oss-120b")

_quota: Dict[str, Dict] = {}
_probe_lock = asyncio.Lock()


def record(model: str, headers) -> None:
    """記下回應標頭裡的剩餘次數（標頭不存在就略過）"""
    try:
        remaining = headers.get("x-ratelimit-remaining-requests")
        limit = headers.get("x-ratelimit-limit-requests")
        if remaining is None:
            return
        _quota[model] = {"remaining": int(remaining), "limit": int(limit or 0), "updated": time.time()}
    except Exception:
        pass


def _silent_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * 8000)  # 0.5 秒
    return buf.getvalue()


async def _probe(model: str) -> None:
    """伺服器剛重啟、還沒有任何紀錄時，打一次最小的請求拿到標頭"""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        if model.startswith("whisper"):
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files={"file": ("probe.wav", _silent_wav(), "audio/wav")},
                data={"model": model},
            )
        else:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
            )
    record(model, resp.headers)


def cached() -> Dict[str, Optional[Dict]]:
    """只回傳已記下的數字，不打 API（每次翻譯回應都附上）"""
    return {"speech": _quota.get(SPEECH_MODEL), "translate": _quota.get(TRANSLATE_MODEL)}


async def snapshot() -> Dict[str, Optional[Dict]]:
    async with _probe_lock:
        for model in (SPEECH_MODEL, TRANSLATE_MODEL):
            if model not in _quota:
                try:
                    await _probe(model)
                except Exception as e:
                    print(f"⚠️ 查詢 Groq 額度失敗 {model}: {e}")
    return {"speech": _quota.get(SPEECH_MODEL), "translate": _quota.get(TRANSLATE_MODEL)}
