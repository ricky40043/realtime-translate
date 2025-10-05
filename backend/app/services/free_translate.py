"""
免費翻譯服務
使用 Google Translate 的公開介面（無需 API 金鑰）
基於 requests 和 BeautifulSoup
"""

import asyncio
import time
import requests
import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote

print("✅ 使用基於 requests 的免費 Google Translate 服務")

class FreeTranslateService:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Google Translate 免費介面的 URL
        self.translate_url = "https://translate.googleapis.com/translate_a/single"
    
    async def translate_text(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """翻譯文字"""
        start_time = time.time()
        
        try:
            # 轉換語言代碼
            target_code = self._convert_lang_code(target_lang)
            source_code = self._convert_lang_code(source_lang) if source_lang else 'auto'
            
            # 使用免費的 Google Translate API
            result = await self._google_translate_free(text, target_code, source_code)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                "text": result["text"],
                "source_lang": result.get("source_lang", source_lang),
                "target_lang": target_lang,
                "latency_ms": latency_ms,
                "quality": result.get("quality", 0.9),
                "provider": "free_google"
            }
            
        except Exception as e:
            print(f"免費翻譯服務錯誤: {e}")
            # 回退到模擬翻譯
            return await self._mock_translate(text, target_lang, source_lang)
    
    async def _google_translate_free(self, text: str, target_code: str, source_code: str) -> Dict:
        """使用免費的 Google Translate API"""
        loop = asyncio.get_event_loop()
        
        # 分段處理長文字
        max_length = 4500
        if len(text) <= max_length:
            result = await loop.run_in_executor(
                None,
                self._translate_single_chunk,
                text, target_code, source_code
            )
            return result
        else:
            # 分段翻譯長文字
            chunks = []
            detected_lang = source_code
            
            for i in range(0, len(text), max_length):
                chunk = text[i:i + max_length]
                result = await loop.run_in_executor(
                    None,
                    self._translate_single_chunk,
                    chunk, target_code, source_code
                )
                chunks.append(result["text"])
                if i == 0:  # 使用第一段的檢測語言
                    detected_lang = result.get("source_lang", source_code)
            
            return {
                "text": "".join(chunks),
                "source_lang": detected_lang,
                "quality": 0.9
            }
    
    def _translate_single_chunk(self, text: str, target_code: str, source_code: str) -> Dict:
        """翻譯單個文字段落"""
        try:
            params = {
                'client': 'gtx',
                'sl': source_code,
                'tl': target_code,
                'dt': 't',
                'q': text
            }
            
            response = self.session.get(self.translate_url, params=params, timeout=10)
            response.raise_for_status()
            
            # 解析回應
            result = response.json()
            
            if result and len(result) > 0 and result[0]:
                # 組合翻譯結果
                translated_text = ""
                for item in result[0]:
                    if item and len(item) > 0:
                        translated_text += item[0]
                
                # 檢測到的源語言
                detected_lang = source_code
                if len(result) > 2 and result[2]:
                    detected_lang = result[2]
                
                return {
                    "text": translated_text,
                    "source_lang": detected_lang,
                    "quality": 0.9
                }
            else:
                raise Exception("無效的翻譯回應")
                
        except Exception as e:
            print(f"Google Translate 免費服務錯誤: {e}")
            # 使用簡單的詞彙替換作為後備
            return {
                "text": self._simple_word_replace(text, target_code),
                "source_lang": source_code,
                "quality": 0.5
            }
    
    def _simple_word_replace(self, text: str, target_code: str) -> str:
        """簡單的詞彙替換（作為後備方案）"""
        # 基本詞彙對照表
        translations = {
            "zh": {
                "hello": "你好", "thank you": "謝謝", "goodbye": "再見",
                "yes": "是", "no": "不", "please": "請", "sorry": "對不起",
                "good": "好", "bad": "壞", "big": "大", "small": "小"
            },
            "en": {
                "你好": "hello", "謝謝": "thank you", "再見": "goodbye",
                "是": "yes", "不": "no", "請": "please", "對不起": "sorry",
                "好": "good", "壞": "bad", "大": "big", "小": "small"
            }
        }
        
        # 簡化的語言代碼
        simple_target = target_code.split('-')[0]
        
        if simple_target in translations:
            result_text = text
            for source_word, target_word in translations[simple_target].items():
                result_text = result_text.replace(source_word, target_word)
            return result_text
        
        return f"[翻譯為{target_code}] {text}"
    
    async def batch_translate(self, text: str, target_langs: List[str], source_lang: Optional[str] = None) -> Dict[str, Dict]:
        """批次翻譯到多個目標語言"""
        tasks = []
        for target_lang in target_langs:
            if target_lang != source_lang:  # 跳過相同語言
                task = self.translate_text(text, target_lang, source_lang)
                tasks.append((target_lang, task))
        
        results = {}
        if tasks:
            completed_tasks = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            
            for i, (target_lang, _) in enumerate(tasks):
                result = completed_tasks[i]
                if isinstance(result, Exception):
                    results[target_lang] = {
                        "text": text,
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "latency_ms": 0,
                        "quality": 0.0,
                        "error": str(result),
                        "provider": f"free_{self.engine}"
                    }
                else:
                    results[target_lang] = result
        
        # 原語言直接回傳原文
        if source_lang and source_lang in target_langs:
            results[source_lang] = {
                "text": text,
                "source_lang": source_lang,
                "target_lang": source_lang,
                "latency_ms": 0,
                "quality": 1.0,
                "provider": f"free_{self.engine}"
            }
        
        return results
    
    def _convert_lang_code(self, lang_code: str) -> str:
        """轉換語言代碼格式"""
        if not lang_code:
            return "auto"
        
        # 免費翻譯服務語言代碼對映
        lang_mapping = {
            "zh-TW": "zh-tw",
            "zh-CN": "zh-cn",
            "zh": "zh-cn",
            "Chinese": "zh-cn",  # 修復：添加 Chinese 對映
            "english": "en",
            "English": "en",
            "en": "en",
            "ja": "ja",
            "japanese": "ja",
            "Japanese": "ja",
            "ko": "ko",
            "korean": "ko",
            "Korean": "ko",
            "es": "es",
            "spanish": "es",
            "Spanish": "es",
            "fr": "fr",
            "french": "fr",
            "French": "fr",
            "de": "de",
            "german": "de",
            "German": "de",
            "it": "it",
            "pt": "pt",
            "ru": "ru",
            "ar": "ar",
            "hi": "hi",
            "th": "th",
            "vi": "vi"
        }
        
        return lang_mapping.get(lang_code, lang_code)
    
    async def _mock_translate(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """模擬翻譯回退"""
        from .mock_translate import mock_translation_service
        return await mock_translation_service.translate_text(text, target_lang, source_lang)

# 全域免費翻譯服務實例
free_translate_service = FreeTranslateService()