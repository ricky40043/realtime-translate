"""
免費翻譯服務
直接呼叫 Google Translate JSON 端點（無需 API key），
使用 async httpx + 連線池，避免爬蟲與執行緒切換開銷。
"""

import asyncio
import os
import time
import httpx
from typing import Dict, List, Optional

print("✅ 翻譯：Groq LLM 為主，Google Translate JSON 端點為備援（async httpx）")

GROQ_TRANSLATE_MODEL = os.getenv("GROQ_TRANSLATE_MODEL", "openai/gpt-oss-120b")

# 給 LLM 的目標語言名稱（明確指定繁/簡，避免模型自行判斷）
_TARGET_NAMES = {
    'zh-TW': 'Traditional Chinese (Taiwan, 繁體中文)',
    'zh-CN': 'Simplified Chinese (简体中文)',
    'en': 'English', 'ja': 'Japanese', 'ko': 'Korean', 'es': 'Spanish',
    'fr': 'French', 'de': 'German', 'it': 'Italian', 'pt': 'Portuguese',
    'ru': 'Russian', 'ar': 'Arabic', 'hi': 'Hindi', 'th': 'Thai',
    'vi': 'Vietnamese', 'id': 'Indonesian', 'ms': 'Malay',
}

# 持久化的 async HTTP 客戶端（連線池複用）
_http_client: Optional[httpx.AsyncClient] = None

async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            http2=False,
        )
    return _http_client


class FreeTranslateService:
    _LANG_MAP = {
        'japanese': 'ja', 'jpn': 'ja',
        'korean': 'ko', 'kor': 'ko',
        'english': 'en', 'eng': 'en',
        'zh-tw': 'zh-TW', 'zh-hk': 'zh-TW',
        'chinese (traditional)': 'zh-TW', 'zho-tw': 'zh-TW',
        'traditional chinese': 'zh-TW',
        'zh-cn': 'zh-CN', 'zh': 'zh-CN', 'zh-sg': 'zh-CN',
        'chinese': 'zh-CN', 'chinese (simplified)': 'zh-CN',
        'zho': 'zh-CN', 'cmn': 'zh-CN', 'simplified chinese': 'zh-CN',
    }

    def _convert_lang(self, code: str) -> str:
        if not code:
            return 'auto'
        lower = code.lower().replace('_', '-')
        if lower in self._LANG_MAP:
            return self._LANG_MAP[lower]
        # zh-TW / zh-CN 保留原樣
        if lower in ('zh-tw', 'zh-cn'):
            return code
        # en-US -> en
        if '-' in lower:
            return lower.split('-')[0]
        return lower

    async def translate_text(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None
    ) -> Dict:
        start = time.time()
        # STT providers sometimes return broad names or wrong language labels.
        # Let Google auto-detect source text for better cross-language speech results.
        src = 'auto'
        tgt = self._convert_lang(target_lang)

        errors = []
        for provider in (self._groq_translate, self._google_translate):
            try:
                translated, provider_name = await provider(text, tgt)
                latency_ms = int((time.time() - start) * 1000)
                print(f"   [Translate] {provider_name} {src}->{tgt} 耗時: {latency_ms}ms")
                return {
                    'text': translated,
                    'source_lang': src,
                    'target_lang': target_lang,
                    'latency_ms': latency_ms,
                    'quality': 0.9,
                    'provider': provider_name,
                }
            except Exception as e:
                errors.append(f"{provider.__name__}: {e}")
                print(f"   [Translate] {provider.__name__} {src}->{tgt} 失敗: {e}")

        latency_ms = int((time.time() - start) * 1000)
        print(f"   [Translate] ❌ 所有翻譯服務皆失敗({latency_ms}ms)，回傳原文")
        return {
            'text': text,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'latency_ms': latency_ms,
            'quality': 0.0,
            'error': '; '.join(errors),
        }

    async def _groq_translate(self, text: str, tgt: str):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY 未設定")
        target_name = _TARGET_NAMES.get(tgt, tgt)
        client = await _get_client()
        resp = await client.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}'},
            json={
                'model': GROQ_TRANSLATE_MODEL,
                'temperature': 0,
                'reasoning_effort': 'low',
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            f"You are a real-time interpreter. Translate the user's message into {target_name}. "
                            "The message is a speech-recognition transcript and may contain mixed languages or small errors; "
                            "translate the intended meaning naturally. If it is already in the target language, return it "
                            "unchanged (but convert Chinese script to the target variant). Output only the translation, "
                            "with no quotes, notes or explanations."
                        ),
                    },
                    {'role': 'user', 'content': text},
                ],
            },
        )
        resp.raise_for_status()
        translated = (resp.json()['choices'][0]['message']['content'] or '').strip()
        if not translated:
            raise RuntimeError("Groq 回傳空白翻譯")
        return translated, f'groq:{GROQ_TRANSLATE_MODEL}'

    async def _google_translate(self, text: str, tgt: str):
        client = await _get_client()
        resp = await client.get(
            'https://translate.googleapis.com/translate_a/single',
            params={
                'client': 'gtx',
                'sl': 'auto',
                'tl': tgt,
                'dt': 't',
                'q': text,
            }
        )
        resp.raise_for_status()
        data = resp.json()
        # data[0] 是句子列表，每個元素 [translated, original, ...]
        return ''.join(seg[0] for seg in data[0] if seg and seg[0]), 'google_translate_json'

    async def batch_translate(
        self,
        text: str,
        target_langs: List[str],
        source_lang: Optional[str] = None
    ) -> Dict[str, Dict]:
        tasks = [self.translate_text(text, lang, source_lang) for lang in target_langs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            lang: (
                results[i] if not isinstance(results[i], Exception)
                else {
                    'text': text,
                    'source_lang': source_lang,
                    'target_lang': lang,
                    'latency_ms': 0,
                    'quality': 0.0,
                    'error': str(results[i]),
                }
            )
            for i, lang in enumerate(target_langs)
        }


# 全域實例
free_translate_service = FreeTranslateService()
