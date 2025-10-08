import httpx
import os
from typing import Dict, List, Optional
import asyncio
from langdetect import detect
import time

class TranslationService:
    def __init__(self):
        self.provider = os.getenv("TRANSLATE_PROVIDER", "google")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.azure_key = os.getenv("AZURE_TRANSLATOR_KEY")
        self.azure_endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT")
        
        # 檢查是否需要使用模擬模式
        self.use_mock = self._should_use_mock()
    
    async def translate_text(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """翻譯文字"""
        # 如果使用模擬模式，委託給模擬服務
        if self.use_mock:
            from .mock_translate import mock_translation_service
            return await mock_translation_service.translate_text(text, target_lang, source_lang)
        
        start_time = time.time()
        
        try:
            if self.provider == "free":
                from .free_translate import free_translate_service
                return await free_translate_service.translate_text(text, target_lang, source_lang)
            elif self.provider == "google_v3":
                from .google_translate_v3 import google_translate_v3_service
                return await google_translate_v3_service.translate_text(text, target_lang, source_lang)
            elif self.provider == "google":
                result = await self._google_translate(text, target_lang, source_lang)
            elif self.provider == "azure":
                result = await self._azure_translate(text, target_lang, source_lang)
            else:
                raise ValueError(f"Unsupported translation provider: {self.provider}")
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                "text": result["text"],
                "source_lang": result.get("source_lang", source_lang),
                "target_lang": target_lang,
                "latency_ms": latency_ms,
                "quality": result.get("quality", 1.0)
            }
        except Exception as e:
            # 如果翻譯失敗，回傳原文
            return {
                "text": text,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "latency_ms": int((time.time() - start_time) * 1000),
                "quality": 0.0,
                "error": str(e)
            }
    
    async def _google_translate(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """使用 Google Translate API"""
        if not self.google_api_key:
            raise ValueError("Google API key not configured")
        
        url = f"https://translation.googleapis.com/language/translate/v2?key={self.google_api_key}"
        
        payload = {
            "q": text,
            "target": target_lang,
            "format": "text"
        }
        
        if source_lang:
            payload["source"] = source_lang
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            translation = data["data"]["translations"][0]
            
            return {
                "text": translation["translatedText"],
                "source_lang": translation.get("detectedSourceLanguage", source_lang),
                "quality": 1.0
            }
    
    async def _azure_translate(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """使用 Azure Translator API"""
        if not self.azure_key or not self.azure_endpoint:
            raise ValueError("Azure Translator credentials not configured")
        
        url = f"{self.azure_endpoint}/translate"
        
        params = {
            "api-version": "3.0",
            "to": target_lang
        }
        
        if source_lang:
            params["from"] = source_lang
        
        headers = {
            "Ocp-Apim-Subscription-Key": self.azure_key,
            "Content-Type": "application/json"
        }
        
        body = [{"text": text}]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, headers=headers, json=body)
            response.raise_for_status()
            
            data = response.json()
            translation = data[0]["translations"][0]
            
            detected_lang = None
            if "detectedLanguage" in data[0]:
                detected_lang = data[0]["detectedLanguage"]["language"]
            
            return {
                "text": translation["text"],
                "source_lang": detected_lang or source_lang,
                "quality": translation.get("confidence", 1.0)
            }
    
    async def batch_translate(self, text: str, target_langs: List[str], source_lang: Optional[str] = None) -> Dict[str, Dict]:
        """批次翻譯到多個目標語言 - 已優化避免重複翻譯"""
        # 如果使用模擬模式，委託給模擬服務
        if self.use_mock:
            from .mock_translate import mock_translation_service
            return await mock_translation_service.batch_translate(text, target_langs, source_lang)
        
        # 如果使用免費翻譯，使用其批次翻譯
        if self.provider == "free":
            from .free_translate import free_translate_service
            return await free_translate_service.batch_translate(text, target_langs, source_lang)
        
        # 如果使用 Google v3，使用其優化的批次翻譯
        if self.provider == "google_v3":
            from .google_translate_v3 import google_translate_v3_service
            return await google_translate_v3_service.batch_translate(text, target_langs, source_lang)
        
        # 🚀 效能優化：去重和跳過相同語言翻譯
        unique_target_langs = list(set(target_langs))  # 去除重複的目標語言
        skipped_count = len(target_langs) - len(unique_target_langs)
        
        if skipped_count > 0:
            print(f"🔧 翻譯優化 - 去除 {skipped_count} 個重複語言，原始: {len(target_langs)} → 優化後: {len(unique_target_langs)}")
            print(f"   原始語言列表: {target_langs}")
            print(f"   去重後列表: {unique_target_langs}")
        
        tasks = []
        skipped_langs = {}
        translate_count = 0
        
        for target_lang in unique_target_langs:
            # 🎯 優化：跳過源語言 = 目標語言的翻譯
            if target_lang == source_lang:
                print(f"⏭️  跳過翻譯 {source_lang} → {target_lang} (相同語言)")
                skipped_langs[target_lang] = {
                    "text": text,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "latency_ms": 0,
                    "quality": 1.0,
                    "skipped": True,
                    "reason": "same_language"
                }
            else:
                task = self.translate_text(text, target_lang, source_lang)
                tasks.append((target_lang, task))
                translate_count += 1
        
        print(f"🔧 翻譯優化結果:")
        print(f"   實際需要翻譯: {translate_count} 個語言")
        print(f"   跳過相同語言: {len(skipped_langs)} 個")
        print(f"   效能提升: {((len(target_langs) - translate_count) / len(target_langs) * 100):.1f}%")
        
        results = {}
        
        # 添加跳過的語言結果
        results.update(skipped_langs)
        
        # 執行翻譯任務
        if tasks:
            completed_tasks = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            
            for i, (target_lang, _) in enumerate(tasks):
                result = completed_tasks[i]
                if isinstance(result, Exception):
                    print(f"❌ 翻譯失敗 {target_lang}: {result}")
                    # 處理異常情況
                    results[target_lang] = {
                        "text": text,
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "latency_ms": 0,
                        "quality": 0.0,
                        "error": str(result)
                    }
                else:
                    results[target_lang] = result
        
        # 🔄 效能優化：為原始的重複語言建立對映
        final_results = {}
        for original_lang in target_langs:
            if original_lang in results:
                # 復用已翻譯的結果
                final_results[original_lang] = results[original_lang].copy()
                # 移除內部標記
                if "skipped" in final_results[original_lang]:
                    del final_results[original_lang]["skipped"]
                    del final_results[original_lang]["reason"]
        
        return final_results
    
    def _should_use_mock(self) -> bool:
        """檢查是否應該使用模擬翻譯服務"""
        # 如果明確設定為 mock 模式
        if self.provider == "mock":
            return True
        
        # 如果是 Google v3 但沒有 Google Cloud 設定
        if self.provider == "google_v3":
            if not os.getenv("GOOGLE_CLOUD_PROJECT"):
                print("⚠️  GOOGLE_CLOUD_PROJECT 未設定，使用模擬翻譯服務")
                return True
            if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                print("⚠️  GOOGLE_APPLICATION_CREDENTIALS 未設定，使用模擬翻譯服務")
                return True
            return False
        
        # 如果是 Google v2 但沒有 API key
        if self.provider == "google" and not self.google_api_key:
            print("⚠️  Google API key 未設定，使用模擬翻譯服務")
            return True
        
        # 如果是 Azure 但沒有設定
        if self.provider == "azure" and (not self.azure_key or not self.azure_endpoint):
            print("⚠️  Azure Translator 憑證未設定，使用模擬翻譯服務")
            return True
        
        return False

def detect_language(text: str) -> str:
    """檢測文字語言"""
    try:
        return detect(text)
    except:
        return "en"  # 預設為英文

# 全域翻譯服務實例
translation_service = TranslationService()