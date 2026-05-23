"""
免費翻譯服務
直接呼叫 Google Translate JSON 端點（無需 API key），
使用 async httpx + 連線池，避免爬蟲與執行緒切換開銷。
"""

import asyncio
import time
import httpx
from typing import Dict, List, Optional

print("✅ 使用 Google Translate JSON 端點（async httpx）")

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

        try:
            client = await _get_client()
            resp = await client.get(
                'https://translate.googleapis.com/translate_a/single',
                params={
                    'client': 'gtx',
                    'sl': src,
                    'tl': tgt,
                    'dt': 't',
                    'q': text,
                }
            )
            resp.raise_for_status()
            data = resp.json()
            # data[0] 是句子列表，每個元素 [translated, original, ...]
            translated = ''.join(seg[0] for seg in data[0] if seg and seg[0])
            latency_ms = int((time.time() - start) * 1000)
            print(f"   [Translate] {src}->{tgt} 耗時: {latency_ms}ms")

            return {
                'text': translated,
                'source_lang': src,
                'target_lang': target_lang,
                'latency_ms': latency_ms,
                'quality': 0.9,
                'provider': 'google_translate_json',
            }

        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            print(f"   [Translate] {src}->{tgt} 失敗({latency_ms}ms): {e}")
            return {
                'text': text,
                'source_lang': source_lang,
                'target_lang': target_lang,
                'latency_ms': latency_ms,
                'quality': 0.0,
                'error': str(e),
            }

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
