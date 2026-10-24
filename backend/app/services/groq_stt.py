"""
Groq 語音辨識服務
使用 Groq API 進行語音轉文字
"""

import os
import time
import asyncio
from typing import Dict, Optional
import tempfile
from groq import Groq, RateLimitError

# 實測：靜音約 0.7、正常說話約 0.02
NO_SPEECH_THRESHOLD = 0.5
MAX_COMPRESSION_RATIO = 2.4

class GroqSTTService:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.use_mock = self._should_use_mock()
        
        if not self.use_mock:
            try:
                self.client = Groq(api_key=self.api_key)
                print("✅ Groq STT API 初始化成功")
            except Exception as e:
                print(f"❌ Groq STT API 初始化失敗: {e}")
                self.use_mock = True
    
    async def transcribe_audio(self, audio_data: bytes, content_type: str = "audio/webm", 
                             language_code: str = "zh-TW", prompt: Optional[str] = None,
                             model: Optional[str] = None) -> Dict:
        """使用 Groq API 進行語音轉文字；model 可指定較快的 whisper-large-v3-turbo（額度與 large-v3 分開算）"""
        if self.use_mock:
            return await self._mock_transcribe(audio_data, language_code)
        
        start_time = time.time()
        
        try:
            # 根據內容類型決定檔案後綴
            suffix = self._get_file_suffix(content_type)
            print(f"🎤 處理音頻格式: {content_type} -> {suffix}")
            
            # 將音頻資料寫入臨時檔案
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # 使用 Groq STT API
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, 
                    self._groq_transcribe_sync,
                    temp_file_path, language_code, prompt, model
                )
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                return {
                    "text": result["text"],
                    "confidence": result.get("confidence", 0.9),
                    "language": result.get("language", language_code),
                    "no_speech_prob": result.get("no_speech_prob", 0.0),
                    "rate_limited": result.get("rate_limited", False),
                    "latency_ms": latency_ms,
                    "provider": "groq"
                }
                
            finally:
                # 清理臨時檔案
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                    
        except Exception as e:
            print(f"Groq STT 錯誤: {e}")
            # 回退到模擬轉錄
            return await self._mock_transcribe(audio_data, language_code)
    
    def _groq_transcribe_sync(self, audio_file_path: str, language_code: str, prompt: Optional[str] = None,
                              model: Optional[str] = None) -> Dict:
        """同步執行 Groq STT API 調用"""
        try:
            # 開啟音頻檔案
            with open(audio_file_path, "rb") as file:
                converted_lang = self._convert_lang_code(language_code)
                kwargs = {
                    "file": file,
                    "model": model or "whisper-large-v3",
                    "response_format": "verbose_json",
                    "temperature": 0.0
                }
                if converted_lang:
                    kwargs["language"] = converted_lang
                if prompt:
                    # 前一段的文字當上下文，讓被切開的句子接得順
                    kwargs["prompt"] = prompt
                # 不傳 language 時 Whisper 自動偵測
                # 指定 model 的是講話中的即時預覽：被限速就直接放棄，不要卡在 SDK 的自動重試
                client = self.client.with_options(max_retries=0) if model else self.client
                transcription = client.audio.transcriptions.create(**kwargs)
                
                # 解析回應
                text = transcription.text
                confidence = getattr(transcription, 'confidence', 0.9)
                detected_language = getattr(transcription, 'language', language_code)

                # Whisper 在沒人講話（安靜、雜音）時會編字幕（「作詞 李宗盛」「請訂閱」），
                # 每段都附「沒有語音的機率」，高的段落直接丟掉；壓縮比過高代表同一句一直重複
                segments = getattr(transcription, 'segments', None) or []
                no_speech = 0.0
                if segments and isinstance(segments[0], dict):
                    no_speech = max(s.get("no_speech_prob", 0.0) for s in segments)
                    kept = [s for s in segments
                            if s.get("no_speech_prob", 0.0) < NO_SPEECH_THRESHOLD
                            and s.get("compression_ratio", 0.0) < MAX_COMPRESSION_RATIO]
                    if len(kept) != len(segments):
                        dropped = [s.get("text", "") for s in segments if s not in kept]
                        print(f"🔇 [STT] 丟棄疑似幻覺段落: {dropped}")
                        text = "".join(s.get("text", "") for s in kept)

                return {
                    "text": text,
                    "confidence": confidence,
                    "language": detected_language,
                    "no_speech_prob": no_speech
                }
                
        except RateLimitError as e:
            print(f"⏳ Groq 轉錄超過速率限制: {e}")
            return {"text": "", "confidence": 0.0, "language": language_code, "rate_limited": True}
        except Exception as e:
            print(f"❌ Groq 同步轉錄錯誤: {e}")
            # 失敗就回空字串（會被過濾掉），不要編造假文字
            return {"text": "", "confidence": 0.0, "language": language_code}
    
    def _convert_lang_code(self, lang_code: str) -> str:
        """轉換語言代碼格式以符合 Groq API，回傳 None 表示自動偵測"""
        if not lang_code:
            return None  # None = 讓 Whisper 自動偵測語言
        
        # Groq/Whisper 語言代碼對映
        lang_mapping = {
            "zh-TW": "zh",
            "zh-CN": "zh", 
            "zh": "zh",
            "en": "en",
            "en-US": "en",
            "ja": "ja",
            "ja-JP": "ja",
            "ko": "ko",
            "ko-KR": "ko",
            "es": "es",
            "fr": "fr",
            "de": "de",
            "it": "it",
            "pt": "pt",
            "ru": "ru",
            "ar": "ar",
            "hi": "hi",
            "th": "th",
            "vi": "vi",
            "id": "id",
            "ms": "ms",
            "my": "my",
            "yue": "yue"
        }
        
        return lang_mapping.get(lang_code, lang_code.split("-")[0].lower())
    
    def _get_file_suffix(self, content_type: str) -> str:
        """根據內容類型獲取檔案後綴"""
        type_mapping = {
            'audio/wav': '.wav',
            'audio/mp4': '.m4a', 
            'audio/mpeg': '.mp3',
            'audio/webm': '.webm',
            'audio/ogg': '.ogg',
            'audio/x-wav': '.wav',
            'audio/vnd.wav': '.wav'
        }
        
        # 優先匹配完整類型
        if content_type in type_mapping:
            return type_mapping[content_type]
        
        # 部分匹配
        for mime_type, suffix in type_mapping.items():
            if content_type.startswith(mime_type.split('/')[0]) and mime_type.split('/')[1] in content_type:
                return suffix
        
        return '.webm'  # 預設
    
    async def _mock_transcribe(self, audio_data: bytes, language_code: str) -> Dict:
        """模擬語音轉錄回退"""
        from .free_stt import free_speech_service
        return await free_speech_service.transcribe_audio(audio_data, "audio/webm", language_code)
    
    def _should_use_mock(self) -> bool:
        """檢查是否應該使用模擬服務"""
        if not self.api_key:
            print("⚠️  GROQ_API_KEY 未設定，使用模擬語音轉文字服務")
            return True
        
        return False

# 全域 Groq STT 服務實例
groq_stt_service = GroqSTTService()