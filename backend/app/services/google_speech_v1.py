"""
Google Cloud Speech-to-Text API v1 服務
支援批次轉錄和即時串流
"""

import os
import time
import asyncio
from typing import Dict, Optional, AsyncGenerator
from google.cloud import speech_v1
from google.oauth2 import service_account
import base64

class GoogleSpeechV1Service:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        # 檢查認證設定
        self.use_mock = self._should_use_mock()
        
        if not self.use_mock:
            try:
                # 初始化客戶端
                if self.service_account_path and os.path.exists(self.service_account_path):
                    credentials = service_account.Credentials.from_service_account_file(
                        self.service_account_path
                    )
                    self.client = speech_v1.SpeechClient(credentials=credentials)
                else:
                    # 使用預設認證
                    self.client = speech_v1.SpeechClient()
                
                print("✅ Google Speech v1 API 初始化成功")
            except Exception as e:
                print(f"❌ Google Speech v1 API 初始化失敗: {e}")
                self.use_mock = True
    
    async def transcribe_audio(self, audio_data: bytes, content_type: str = "audio/webm", 
                             language_code: str = "zh-TW") -> Dict:
        """轉錄音頻為文字"""
        if self.use_mock:
            return await self._mock_transcribe(audio_data, language_code)
        
        start_time = time.time()
        
        try:
            # 轉換語言代碼
            language_code = self._convert_lang_code(language_code)
            
            # 根據 content_type 設定編碼格式
            encoding = self._get_audio_encoding(content_type)
            
            # 建立音頻配置
            config = speech_v1.RecognitionConfig(
                encoding=encoding,
                sample_rate_hertz=48000,  # WebRTC 預設取樣率
                language_code=language_code,
                alternative_language_codes=["en-US", "zh-CN", "ja-JP", "ko-KR"],
                enable_automatic_punctuation=True,
                enable_word_confidence=True,
                model="latest_long",  # 適合較長的音頻
                use_enhanced=True  # 使用增強模型
            )
            
            # 建立音頻物件
            audio = speech_v1.RecognitionAudio(content=audio_data)
            
            # 執行轉錄
            request = speech_v1.RecognizeRequest(
                config=config,
                audio=audio
            )
            
            # 在執行緒池中執行同步 API 調用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self.client.recognize,
                request
            )
            
            # 處理回應
            if response.results:
                result = response.results[0]
                alternative = result.alternatives[0]
                
                # 計算平均信心度
                confidence = alternative.confidence if hasattr(alternative, 'confidence') else 0.9
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                return {
                    "text": alternative.transcript,
                    "confidence": confidence,
                    "language": language_code,
                    "latency_ms": latency_ms,
                    "provider": "google_speech_v1"
                }
            else:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "language": language_code,
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "google_speech_v1"
                }
                
        except Exception as e:
            print(f"Google Speech v1 錯誤: {e}")
            # 回退到模擬轉錄
            return await self._mock_transcribe(audio_data, language_code)
    
    async def streaming_recognize(self, audio_generator: AsyncGenerator[bytes, None], 
                                language_code: str = "zh-TW") -> AsyncGenerator[Dict, None]:
        """即時語音轉錄串流"""
        if self.use_mock:
            async for result in self._mock_streaming_transcribe(audio_generator, language_code):
                yield result
            return
        
        try:
            # 轉換語言代碼
            language_code = self._convert_lang_code(language_code)
            
            # 建立串流配置
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                sample_rate_hertz=48000,
                language_code=language_code,
                alternative_language_codes=["en-US", "zh-CN", "ja-JP"],
                enable_automatic_punctuation=True,
                enable_word_confidence=True,
                model="latest_short",  # 適合即時轉錄
                use_enhanced=True
            )
            
            streaming_config = speech_v1.StreamingRecognitionConfig(
                config=config,
                interim_results=True,  # 顯示中間結果
                single_utterance=False  # 持續監聽
            )
            
            # 建立請求生成器
            async def request_generator():
                # 首先發送配置
                yield speech_v1.StreamingRecognizeRequest(streaming_config=streaming_config)
                
                # 然後發送音頻數據
                async for audio_chunk in audio_generator:
                    yield speech_v1.StreamingRecognizeRequest(audio_content=audio_chunk)
            
            # 執行串流識別
            loop = asyncio.get_event_loop()
            responses = await loop.run_in_executor(
                None,
                self.client.streaming_recognize,
                request_generator()
            )
            
            # 處理串流回應
            for response in responses:
                for result in response.results:
                    alternative = result.alternatives[0]
                    
                    yield {
                        "text": alternative.transcript,
                        "confidence": alternative.confidence if hasattr(alternative, 'confidence') else 0.9,
                        "is_final": result.is_final,
                        "language": language_code,
                        "provider": "google_speech_v1"
                    }
                    
        except Exception as e:
            print(f"串流轉錄錯誤: {e}")
            # 回退到模擬串流
            async for result in self._mock_streaming_transcribe(audio_generator, language_code):
                yield result
    
    def _get_audio_encoding(self, content_type: str) -> speech_v1.RecognitionConfig.AudioEncoding:
        """根據 content type 決定音頻編碼格式"""
        if "webm" in content_type.lower():
            return speech_v1.RecognitionConfig.AudioEncoding.WEBM_OPUS
        elif "mp4" in content_type.lower():
            return speech_v1.RecognitionConfig.AudioEncoding.MP3
        elif "wav" in content_type.lower():
            return speech_v1.RecognitionConfig.AudioEncoding.LINEAR16
        elif "flac" in content_type.lower():
            return speech_v1.RecognitionConfig.AudioEncoding.FLAC
        else:
            # 預設使用 WEBM_OPUS
            return speech_v1.RecognitionConfig.AudioEncoding.WEBM_OPUS
    
    def _convert_lang_code(self, lang_code: str) -> str:
        """轉換語言代碼格式以符合 Google Cloud Speech API"""
        if not lang_code:
            return "zh-TW"
        
        # Google Cloud Speech 語言代碼對映
        lang_mapping = {
            "zh-TW": "zh-TW",
            "zh-CN": "zh-CN",
            "zh": "zh-CN",
            "en": "en-US",
            "en-US": "en-US",
            "ja": "ja-JP",
            "ja-JP": "ja-JP",
            "ko": "ko-KR",
            "ko-KR": "ko-KR",
            "es": "es-ES",
            "fr": "fr-FR",
            "de": "de-DE",
            "it": "it-IT",
            "pt": "pt-PT",
            "ru": "ru-RU"
        }
        
        return lang_mapping.get(lang_code, "zh-TW")
    
    async def _mock_transcribe(self, audio_data: bytes, language_code: str) -> Dict:
        """模擬語音轉錄回退"""
        from .stt import stt_service
        return await stt_service._mock_transcribe(audio_data, language_code)
    
    async def _mock_streaming_transcribe(self, audio_generator: AsyncGenerator[bytes, None], 
                                       language_code: str) -> AsyncGenerator[Dict, None]:
        """模擬串流轉錄"""
        # 模擬即時轉錄效果
        accumulated_audio = b""
        
        async for audio_chunk in audio_generator:
            accumulated_audio += audio_chunk
            
            # 模擬中間結果
            yield {
                "text": "正在識別中...",
                "confidence": 0.5,
                "is_final": False,
                "language": language_code,
                "provider": "mock_streaming"
            }
            
            # 模擬延遲
            await asyncio.sleep(0.1)
        
        # 模擬最終結果
        final_result = await self._mock_transcribe(accumulated_audio, language_code)
        final_result["is_final"] = True
        yield final_result
    
    def _should_use_mock(self) -> bool:
        """檢查是否應該使用模擬服務"""
        if not self.project_id:
            print("⚠️  GOOGLE_CLOUD_PROJECT 未設定，使用模擬語音服務")
            return True
        
        if not self.service_account_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            print("⚠️  Google Cloud 認證未設定，使用模擬語音服務")
            return True
        
        return False

# 全域 Google Speech v1 服務實例
google_speech_v1_service = GoogleSpeechV1Service()