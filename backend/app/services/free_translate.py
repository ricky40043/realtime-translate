"""
免費翻譯服務
使用 deep-translator 的公開介面（無需 API 金鑰）
"""

import asyncio
import time
from typing import Dict, List, Optional
from deep_translator import GoogleTranslator

print("✅ 使用基於 deep-translator 的免費 Google Translate 服務")

class FreeTranslateService:
    def __init__(self):
        pass
    
    async def translate_text(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """翻譯文字"""
        start_time = time.time()
        
        try:
            # 轉換語言代碼
            target_code = self._convert_lang_code(target_lang)
            source_code = 'auto'  # 強制使用 auto 讓 Google 自動檢測語言，避免 STT 誤判導致翻譯失敗
            
            # 使用 deep-translator 進行翻譯（它內部會處理分段和各種 URL 問題）
            loop = asyncio.get_event_loop()
            translated_text = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source=source_code, target=target_code).translate(text)
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                "text": translated_text,
                "source_lang": "auto",
                "target_lang": target_lang,
                "latency_ms": latency_ms,
                "quality": 0.9,
                "provider": "free_google_deep_translator"
            }
            
        except Exception as e:
            print(f"免費翻譯服務錯誤: {e}")
            # 回退到模擬翻譯
            return await self._mock_translate(text, target_lang, source_lang)
    
    async def batch_translate(self, text: str, target_langs: List[str], source_lang: Optional[str] = None) -> Dict[str, Dict]:
        """批次翻譯到多個目標語言"""
        tasks = []
        for target_lang in target_langs:
            # 即使 target_lang 和 source_lang 相同也嘗試翻譯，因為 source_lang 有可能是錯的
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
                        "provider": "free_google_deep_translator"
                    }
                else:
                    results[target_lang] = result
        
        return results
    
    def _convert_lang_code(self, lang_code: str) -> str:
        """轉換語言代碼格式為 deep-translator (Google) 支援的格式"""
        if not lang_code:
            return "auto"
        
        lang_code = lang_code.replace('_', '-')
        
        # 繁體中文特例
        if lang_code.lower() in ["zh-tw", "zh-hk", "chinese (traditional)", "zho-tw", "traditional chinese"]:
            return "zh-TW"
            
        # 簡體中文特例
        if lang_code.lower() in ["zh-cn", "zh", "zh-sg", "chinese", "chinese (simplified)", "zho", "cmn", "simplified chinese"]:
            return "zh-CN"
            
        # 處理普通帶有國碼的情況，截斷保留主要語系 (例如 en-US -> en, ja-JP -> ja)
        if '-' in lang_code:
            return lang_code.split('-')[0].lower()
            
        return lang_code.lower()
    
    async def _mock_translate(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """模擬翻譯回退"""
        from .mock_translate import mock_translation_service
        return await mock_translation_service.translate_text(text, target_lang, source_lang)

# 全域免費翻譯服務實例
free_translate_service = FreeTranslateService()