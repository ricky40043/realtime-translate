"""
模擬翻譯服務 - 用於測試和開發
當沒有真實 API 金鑰時使用
"""

import asyncio
import time
from typing import Dict, List, Optional

class MockTranslationService:
    """模擬翻譯服務，提供假的翻譯結果"""
    
    def __init__(self):
        # 模擬翻譯對照表
        self.mock_translations = {
            # 中文 -> 其他語言
            "你好": {
                "en": "Hello",
                "ja": "こんにちは", 
                "ko": "안녕하세요",
                "es": "Hola",
                "fr": "Bonjour"
            },
            "謝謝": {
                "en": "Thank you",
                "ja": "ありがとう",
                "ko": "감사합니다", 
                "es": "Gracias",
                "fr": "Merci"
            },
            "再見": {
                "en": "Goodbye",
                "ja": "さようなら",
                "ko": "안녕히 가세요",
                "es": "Adiós", 
                "fr": "Au revoir"
            },
            # 英文 -> 其他語言
            "hello": {
                "zh-TW": "你好",
                "zh-CN": "你好", 
                "ja": "こんにちは",
                "ko": "안녕하세요",
                "es": "Hola",
                "fr": "Bonjour"
            },
            "thank you": {
                "zh-TW": "謝謝",
                "zh-CN": "谢谢",
                "ja": "ありがとう", 
                "ko": "감사합니다",
                "es": "Gracias",
                "fr": "Merci"
            },
            "goodbye": {
                "zh-TW": "再見",
                "zh-CN": "再见",
                "ja": "さようなら",
                "ko": "안녕히 가세요", 
                "es": "Adiós",
                "fr": "Au revoir"
            },
            # 日文 -> 其他語言  
            "こんにちは": {
                "zh-TW": "你好",
                "zh-CN": "你好",
                "en": "Hello",
                "ko": "안녕하세요",
                "es": "Hola"
            },
            "ありがとう": {
                "zh-TW": "謝謝", 
                "zh-CN": "谢谢",
                "en": "Thank you",
                "ko": "감사합니다",
                "es": "Gracias"
            }
        }
    
    async def translate_text(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """模擬翻譯文字"""
        start_time = time.time()
        
        # 模擬 API 延遲
        await asyncio.sleep(0.1 + (len(text) * 0.001))  # 根據文字長度調整延遲
        
        # 檢查是否有預定義翻譯
        text_lower = text.lower().strip()
        translated_text = text  # 預設回傳原文
        detected_lang = source_lang or self._detect_language(text)
        
        # 尋找匹配的翻譯
        for key, translations in self.mock_translations.items():
            if key.lower() in text_lower or text_lower in key.lower():
                if target_lang in translations:
                    # 替換匹配的部分
                    translated_text = text.replace(key, translations[target_lang])
                    break
        
        # 如果沒有找到匹配，生成模擬翻譯
        if translated_text == text and target_lang != detected_lang:
            translated_text = self._generate_mock_translation(text, target_lang)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return {
            "text": translated_text,
            "source_lang": detected_lang,
            "target_lang": target_lang,
            "latency_ms": latency_ms,
            "quality": 0.9,  # 模擬高質量翻譯
            "provider": "mock"
        }
    
    async def batch_translate(self, text: str, target_langs: List[str], source_lang: Optional[str] = None) -> Dict[str, Dict]:
        """批次翻譯到多個目標語言"""
        tasks = []
        detected_lang = source_lang or self._detect_language(text)
        
        for target_lang in target_langs:
            if target_lang != detected_lang:  # 跳過相同語言
                task = self.translate_text(text, target_lang, detected_lang)
                tasks.append((target_lang, task))
        
        results = {}
        if tasks:
            completed_tasks = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            
            for i, (target_lang, _) in enumerate(tasks):
                result = completed_tasks[i]
                if isinstance(result, Exception):
                    results[target_lang] = {
                        "text": text,
                        "source_lang": detected_lang,
                        "target_lang": target_lang,
                        "latency_ms": 0,
                        "quality": 0.0,
                        "error": str(result),
                        "provider": "mock"
                    }
                else:
                    results[target_lang] = result
        
        # 原語言直接回傳原文
        if detected_lang and detected_lang in target_langs:
            results[detected_lang] = {
                "text": text,
                "source_lang": detected_lang,
                "target_lang": detected_lang,
                "latency_ms": 0,
                "quality": 1.0,
                "provider": "mock"
            }
        
        return results
    
    def _detect_language(self, text: str) -> str:
        """簡單的語言檢測"""
        # 檢測中文字符
        if any('\u4e00' <= char <= '\u9fff' for char in text):
            # 簡單區分繁體和簡體（這裡簡化處理）
            simplified_chars = ['简', '国', '学', '门', '车', '书']
            if any(char in text for char in simplified_chars):
                return "zh-CN"
            return "zh-TW"
        
        # 檢測日文字符
        if any('\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' for char in text):
            return "ja"
        
        # 檢測韓文字符
        if any('\uac00' <= char <= '\ud7af' for char in text):
            return "ko"
        
        # 預設為英文
        return "en"
    
    def _generate_mock_translation(self, text: str, target_lang: str) -> str:
        """生成模擬翻譯結果"""
        prefixes = {
            "zh-TW": "【翻譯】",
            "zh-CN": "【翻译】", 
            "ja": "【翻訳】",
            "ko": "【번역】",
            "en": "[Translated]",
            "es": "[Traducido]",
            "fr": "[Traduit]",
            "de": "[Übersetzt]"
        }
        
        prefix = prefixes.get(target_lang, "[Translated]")
        return f"{prefix} {text}"

# 全域模擬翻譯服務實例
mock_translation_service = MockTranslationService()