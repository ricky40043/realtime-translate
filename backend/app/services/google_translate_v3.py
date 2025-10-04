"""
Google Cloud Translation API v3 服務
使用 Service Account 認證，支援更多功能
"""

import os
import time
import asyncio
from typing import Dict, List, Optional
from google.cloud import translate_v3
from google.oauth2 import service_account
import json

class GoogleTranslateV3Service:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.location = "global"  # 或 "us-central1" 等
        
        # 檢查認證設定
        self.use_mock = self._should_use_mock()
        
        if not self.use_mock:
            try:
                # 初始化客戶端
                if self.service_account_path and os.path.exists(self.service_account_path):
                    credentials = service_account.Credentials.from_service_account_file(
                        self.service_account_path
                    )
                    self.client = translate_v3.TranslationServiceClient(credentials=credentials)
                else:
                    # 使用預設認證（適用於 Google Cloud 環境）
                    self.client = translate_v3.TranslationServiceClient()
                
                self.parent = f"projects/{self.project_id}/locations/{self.location}"
                print("✅ Google Translate v3 API 初始化成功")
            except Exception as e:
                print(f"❌ Google Translate v3 API 初始化失敗: {e}")
                self.use_mock = True
    
    async def translate_text(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """翻譯文字"""
        if self.use_mock:
            return await self._mock_translate(text, target_lang, source_lang)
        
        start_time = time.time()
        
        try:
            # 轉換語言代碼格式（zh-TW -> zh-TW, en -> en）
            target_language_code = self._convert_lang_code(target_lang)
            source_language_code = self._convert_lang_code(source_lang) if source_lang else None
            
            request = {
                "parent": self.parent,
                "contents": [text],
                "mime_type": "text/plain",
                "target_language_code": target_language_code,
            }
            
            if source_language_code:
                request["source_language_code"] = source_language_code
            
            # 在執行緒池中執行同步 API 調用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                self.client.translate_text,
                request
            )
            
            # 處理回應
            translation = response.translations[0]
            translated_text = translation.translated_text
            detected_source_lang = translation.detected_language_code if hasattr(translation, 'detected_language_code') else source_lang
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                "text": translated_text,
                "source_lang": detected_source_lang or source_lang,
                "target_lang": target_lang,
                "latency_ms": latency_ms,
                "quality": 1.0,
                "provider": "google_v3"
            }
            
        except Exception as e:
            print(f"Google Translate v3 錯誤: {e}")
            # 回退到模擬翻譯
            return await self._mock_translate(text, target_lang, source_lang)
    
    async def batch_translate(self, text: str, target_langs: List[str], source_lang: Optional[str] = None) -> Dict[str, Dict]:
        """批次翻譯到多個目標語言"""
        if self.use_mock:
            from .mock_translate import mock_translation_service
            return await mock_translation_service.batch_translate(text, target_langs, source_lang)
        
        # Google Cloud v3 支援批次翻譯
        try:
            # 轉換語言代碼
            target_language_codes = [self._convert_lang_code(lang) for lang in target_langs if lang != source_lang]
            source_language_code = self._convert_lang_code(source_lang) if source_lang else None
            
            if not target_language_codes:
                return {}
            
            # 為每個目標語言執行翻譯
            results = {}
            tasks = []
            
            for target_lang in target_langs:
                if target_lang != source_lang:
                    task = self.translate_text(text, target_lang, source_lang)
                    tasks.append((target_lang, task))
            
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
                            "provider": "google_v3"
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
                    "provider": "google_v3"
                }
            
            return results
            
        except Exception as e:
            print(f"批次翻譯錯誤: {e}")
            # 回退到逐一翻譯
            results = {}
            for target_lang in target_langs:
                if target_lang != source_lang:
                    result = await self.translate_text(text, target_lang, source_lang)
                    results[target_lang] = result
            return results
    
    def _convert_lang_code(self, lang_code: str) -> str:
        """轉換語言代碼格式以符合 Google Cloud API"""
        if not lang_code:
            return "en"
        
        # Google Cloud 語言代碼對映
        lang_mapping = {
            "zh-TW": "zh-TW",
            "zh-CN": "zh-CN", 
            "zh": "zh-CN",
            "en": "en",
            "ja": "ja",
            "ko": "ko",
            "es": "es",
            "fr": "fr",
            "de": "de",
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
    
    def _should_use_mock(self) -> bool:
        """檢查是否應該使用模擬服務"""
        # 檢查必要的環境變數
        if not self.project_id:
            print("⚠️  GOOGLE_CLOUD_PROJECT 未設定，使用模擬翻譯服務")
            return True
        
        if not self.service_account_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            print("⚠️  Google Cloud 認證未設定，使用模擬翻譯服務")
            return True
        
        return False

# 全域 Google Translate v3 服務實例
google_translate_v3_service = GoogleTranslateV3Service()