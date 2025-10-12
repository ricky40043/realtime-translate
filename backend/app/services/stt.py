"""
語音轉文字 (STT) 服務
支援 Google Speech-to-Text 和 Azure Speech Services
"""

import os
import httpx
import base64
import json
import time
from typing import Dict, Optional, List
import asyncio

class STTService:
    def __init__(self):
        self.provider = os.getenv("STT_PROVIDER", "google")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.azure_key = os.getenv("AZURE_SPEECH_KEY")
        self.azure_region = os.getenv("AZURE_SPEECH_REGION")
        
        # 檢查是否需要使用模擬模式
        self.use_mock = False
        # self.use_mock = self._should_use_mock()
    
    async def transcribe_audio(self, audio_data: bytes, content_type: str = "audio/webm", 
                             language_code: str = "zh-TW") -> Dict:
        """轉錄音頻為文字"""
        if self.use_mock:
            return await self._mock_transcribe(audio_data, language_code)
        
        start_time = time.time()
        
        try:
            if self.provider == "groq":
                from .groq_stt import groq_stt_service
                return await groq_stt_service.transcribe_audio(audio_data, content_type, language_code)
            elif self.provider == "free":
                from .free_stt import free_speech_service
                return await free_speech_service.transcribe_audio(audio_data, content_type, language_code)
            elif self.provider == "google_v1":
                from .google_speech_v1 import google_speech_v1_service
                return await google_speech_v1_service.transcribe_audio(audio_data, content_type, language_code)
            elif self.provider == "google":
                result = await self._google_speech_to_text(audio_data, content_type, language_code)
            elif self.provider == "azure":
                result = await self._azure_speech_to_text(audio_data, content_type, language_code)
            else:
                raise ValueError(f"Unsupported STT provider: {self.provider}")
            
            latency_ms = int((time.time() - start_time) * 1000)
            result["latency_ms"] = latency_ms
            
            return result
            
        except Exception as e:
            return {
                "text": "",
                "confidence": 0.0,
                "language": language_code,
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
                "provider": self.provider
            }
    
    async def _google_speech_to_text(self, audio_data: bytes, content_type: str, language_code: str) -> Dict:
        """使用 Google Speech-to-Text API"""
        if not self.google_api_key:
            raise ValueError("Google API key not configured")
        
        # 將音頻轉為 base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        # 根據 content_type 設定編碼格式
        encoding = "WEBM_OPUS" if "webm" in content_type else "LINEAR16"
        
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={self.google_api_key}"
        
        payload = {
            "config": {
                "encoding": encoding,
                "sampleRateHertz": 48000,
                "languageCode": language_code,
                "alternativeLanguageCodes": ["en-US", "zh-CN", "ja-JP"],
                "enableAutomaticPunctuation": True,
                "model": "latest_long"
            },
            "audio": {
                "content": audio_base64
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            
            data = response.json()
            
            if "results" in data and data["results"]:
                result = data["results"][0]
                alternative = result["alternatives"][0]
                
                return {
                    "text": alternative["transcript"],
                    "confidence": alternative.get("confidence", 1.0),
                    "language": language_code,
                    "provider": "google"
                }
            else:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "language": language_code,
                    "provider": "google"
                }
    
    async def _azure_speech_to_text(self, audio_data: bytes, content_type: str, language_code: str) -> Dict:
        """使用 Azure Speech Services"""
        if not self.azure_key or not self.azure_region:
            raise ValueError("Azure Speech credentials not configured")
        
        url = f"https://{self.azure_region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        
        headers = {
            "Ocp-Apim-Subscription-Key": self.azure_key,
            "Content-Type": content_type,
            "Accept": "application/json"
        }
        
        params = {
            "language": language_code,
            "format": "detailed"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, 
                headers=headers, 
                params=params, 
                content=audio_data,
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("RecognitionStatus") == "Success":
                return {
                    "text": data["DisplayText"],
                    "confidence": data.get("Confidence", 1.0),
                    "language": language_code,
                    "provider": "azure"
                }
            else:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "language": language_code,
                    "provider": "azure"
                }
    
    async def _mock_transcribe(self, audio_data: bytes, language_code: str) -> Dict:
        """模擬語音轉文字"""
        # 模擬處理延遲
        await asyncio.sleep(0.5)
        
        # 根據音頻大小生成模擬文字
        audio_size = len(audio_data)
        
        mock_texts = {
            "zh-TW": [
                "你好，這是一段測試語音",
                "謝謝你使用我們的語音轉文字服務",
                "今天天氣真不錯",
                "我正在測試即時翻譯功能"
            ],
            "en": [
                "Hello, this is a test speech",
                "Thank you for using our speech-to-text service", 
                "The weather is really nice today",
                "I am testing the real-time translation feature"
            ],
            "ja": [
                "こんにちは、これはテスト音声です",
                "音声認識サービスをご利用いただき、ありがとうございます",
                "今日はとても良い天気ですね"
            ]
        }
        
        texts = mock_texts.get(language_code, mock_texts["en"])
        # 根據音頻大小選擇文字
        text_index = min(len(texts) - 1, audio_size // 1000)
        selected_text = texts[text_index]
        
        return {
            "text": selected_text,
            "confidence": 0.95,
            "language": language_code,
            "latency_ms": 500,
            "provider": "mock"
        }
    
    def _should_use_mock(self) -> bool:
        """檢查是否應該使用模擬 STT 服務"""
        # 如果明確設定為 mock 模式
        if self.provider == "mock":
            return True
        
        # 如果是 Groq 服務，不使用 mock
        if self.provider == "groq":
            return False
        
        # 如果是免費服務，不使用 mock
        if self.provider == "free":
            return False
        
        # 如果是 Google v1 但沒有 Google Cloud 設定
        if self.provider == "google_v1":
            if not os.getenv("GOOGLE_CLOUD_PROJECT"):
                print("⚠️  GOOGLE_CLOUD_PROJECT 未設定，使用模擬語音轉文字服務")
                return True
            if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                print("⚠️  GOOGLE_APPLICATION_CREDENTIALS 未設定，使用模擬語音轉文字服務")
                return True
            return False
        
        # 如果是 Google v2 但沒有 API key
        if self.provider == "google" and not self.google_api_key:
            print("⚠️  Google Speech API key 未設定，使用模擬語音轉文字服務")
            return True
        
        # 如果是 Azure 但沒有設定
        if self.provider == "azure" and (not self.azure_key or not self.azure_region):
            print("⚠️  Azure Speech 憑證未設定，使用模擬語音轉文字服務")
            return True
        
        return False

# 全域 STT 服務實例
stt_service = STTService()