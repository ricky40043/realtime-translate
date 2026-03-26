"""
分段語音處理 API
步驟 1: 語音辨識 (STT)
步驟 2: 文字翻譯
"""

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from typing import Optional
from pydantic import BaseModel
import asyncpg
import re
from ..deps import get_db, get_current_user
from ..db.repo import MessageRepo, RoomRepo
from ..services.stt import stt_service
from ..services.translate import translation_service, detect_language
from ..services.router import LanguageRouter
from ..ws.hub import manager

router = APIRouter()

def filter_ai_default_responses(text: str) -> str:
    """
    過濾AI語音辨識模型在無聲音時的預設回應
    這些回應通常出現在空檔案或無聲音檔案的辨識結果中
    """
    print(f"🔍 原始辨識結果: '{text}'")
    if not text or not text.strip():
        return ""
    
    text_cleaned = text.strip()
    
    # 定義需要過濾的完整匹配字串（繁體和簡體都包含）
    exact_filter_list = [
        # 明鏡相關 - 繁體
        "請不吝點贊 訂閱 轉發 打賞支持明鏡與點點欄目",
        "謝謝大家",
        "明鏡與點點欄目",
        "歡迎訂閱我的頻道",
        
        # 明鏡相關 - 簡體  
        "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
        "谢谢大家",
        "明镜与点点栏目",
        "欢迎订阅我的频道",
        
        # 其他常見結束語
        "感謝收看",
        "感谢收看", 
        "下次再見",
        "下次再见",
        "記得訂閱",
        "记得订阅",
        "按讚分享",
        "按赞分享",
        "支持頻道",
        "支持频道",
    ]
    
    # 完整匹配檢查
    for filter_text in exact_filter_list:
        if text_cleaned == filter_text:
            print(f"🚫 完整匹配過濾: '{text_cleaned}'")
            return ""
    
    # # 定義需要過濾的模糊匹配模式
    # filter_patterns = [
    #     # 包含明鏡相關關鍵字的句子
    #     r".*點贊.*訂閱.*轉發.*打賞.*明鏡.*",
    #     r".*点赞.*订阅.*转发.*打赏.*明镜.*",
    #     r".*支持.*明鏡.*點點.*欄目.*",
    #     r".*支持.*明镜.*点点.*栏目.*",
        
    #     # 其他常見的AI預設回應
    #     r".*字幕.*製作.*",
    #     r".*字幕.*制作.*",
    #     r".*影片.*結束.*",
    #     r".*影片.*结束.*",
    #     r"^\.+$",  # 只有句號
    #     r"^，+$",  # 只有逗號
    #     r"^。+$",  # 只有句號（中文）
    #     r"^\s*$",  # 只有空白
        
    #     # 常見的無意義單字輸出
    #     r"^你$",
    #     r"^好$", 
    #     r"^嗯$",
    #     r"^啊$",
    #     r"^呃$",
    #     r"^這個$",
    #     r"^那個$",
    #     r"^这个$",
    #     r"^那个$",
    # ]
    
    # # 檢查是否匹配任何過濾模式
    # for pattern in filter_patterns:
    #     if re.match(pattern, text_cleaned, re.IGNORECASE):
    #         print(f"🚫 模式匹配過濾: '{text_cleaned}' (匹配模式: {pattern})")
    #         return ""
    
    # # 檢查長度過短的回應（少於3個字符的可能是無意義輸出）
    # if len(text_cleaned) <= 2:
    #     print(f"🚫 過濾過短回應: '{text_cleaned}'")
    #     return ""
    
    # # 檢查是否全是重複字符
    # if len(set(text_cleaned)) <= 1:
    #     print(f"🚫 過濾重複字符: '{text_cleaned}'")
    #     return ""
        
    print(f"✅ 通過過濾檢查: '{text_cleaned}'")
        
    return text_cleaned

class STTResponse(BaseModel):
    transcript_id: str
    transcript: str
    confidence: float
    detected_lang: str
    status: str

class TranslateSTTRequest(BaseModel):
    transcript_id: str
    room_id: str
    confirmed_text: str  # 用戶可以修正的文字
    source_lang: str = None

class TranslateResponse(BaseModel):
    message_id: str
    final_text: str
    source_lang: str
    translations_count: int
    status: str

# 暫存 STT 結果（生產環境建議用 Redis）
transcript_cache = {}

@router.post("/stt-only", response_model=STTResponse)
async def speech_to_text_only(
    room_id: str = Form(...),
    language_code: Optional[str] = Form(None),
    audio: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """
    步驟 1: 純語音辨識，不進行翻譯
    用戶可以看到辨識結果並進行修正
    """
    try:
        # 檢查房間是否存在
        room_repo = RoomRepo(db)
        room = await room_repo.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # 檢查檔案類型
        if not audio.content_type or not audio.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="Invalid audio file")
        
        # 讀取音頻資料
        audio_data = await audio.read()
        
        # 限制檔案大小 (10MB)
        if len(audio_data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Audio file too large (max 10MB)")
        
        # 語音轉文字
        stt_result = await stt_service.transcribe_audio(
            audio_data, 
            audio.content_type, 
            language_code
        )
        
        transcript = stt_result["text"]
        confidence = stt_result["confidence"]
        detected_lang = stt_result.get("language", language_code)
        
        # 過濾AI語音辨識模型的預設回應
        print(f"🔍 原始辨識結果: '{transcript}'")
        transcript = filter_ai_default_responses(transcript)
        print(f"🔍 過濾後結果: '{transcript}'")
        
        if not transcript:
            print(f"⚠️ 辨識結果被過濾或為空，跳過翻譯和Socket發送")
            # 回傳成功但不進行任何翻譯或WebSocket處理
            return STTResponse(
                transcript_id="filtered",
                transcript="",
                confidence=0.0,
                detected_lang=detected_lang,
                status="filtered"
            )
        
        # 生成 transcript ID 並暫存結果
        import uuid
        transcript_id = str(uuid.uuid4())
        
        transcript_cache[transcript_id] = {
            "transcript": transcript,
            "confidence": confidence,
            "detected_lang": detected_lang,
            "room_id": room_id,
            "user_id": current_user,
            "timestamp": "now()"
        }
        
        # 透過 WebSocket 發送 STT 結果預覽
        await send_stt_preview(room_id, current_user, transcript, confidence, detected_lang)
        
        return STTResponse(
            transcript_id=transcript_id,
            transcript=transcript,
            confidence=confidence,
            detected_lang=detected_lang,
            status="stt_completed"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT failed: {str(e)}")

@router.post("/translate-stt", response_model=TranslateResponse)
async def translate_transcribed_text(
    request: TranslateSTTRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """
    步驟 2: 將 STT 結果進行翻譯並廣播
    用戶可以在這步之前修正辨識文字
    """
    try:
        # 從快取中取得 STT 結果
        if request.transcript_id not in transcript_cache:
            raise HTTPException(status_code=404, detail="Transcript not found or expired")
        
        stt_data = transcript_cache[request.transcript_id]
        
        # 驗證房間和用戶
        if stt_data["room_id"] != request.room_id or stt_data["user_id"] != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # 檢查房間是否存在
        room_repo = RoomRepo(db)
        room = await room_repo.get_room(request.room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # 使用用戶確認的文字（可能已修正）
        final_text = request.confirmed_text.strip()
        if not final_text:
            raise HTTPException(status_code=400, detail="Confirmed text cannot be empty")
        
        # 語言檢測（如果未指定）
        source_lang = request.source_lang
        if not source_lang:
            source_lang = detect_language(final_text)
        
        # 建立訊息記錄
        message_repo = MessageRepo(db)
        message_id = await message_repo.create_message(
            room_id=request.room_id,
            speaker_id=current_user,
            text=final_text,
            source_lang=source_lang,
            is_final=True
        )
        
        # 在背景處理翻譯
        background_tasks.add_task(
            process_speech_translation,
            message_id, request.room_id, current_user, 
            final_text, source_lang, db
        )
        
        # 清除快取
        del transcript_cache[request.transcript_id]
        
        # 計算預期翻譯數量
        online_users = await manager.get_room_users(request.room_id)
        lang_router = LanguageRouter(db)
        target_langs = await lang_router.get_all_target_languages(request.room_id, current_user, online_users)
        
        return TranslateResponse(
            message_id=message_id,
            final_text=final_text,
            source_lang=source_lang,
            translations_count=len(target_langs),
            status="translation_processing"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

async def send_stt_preview(room_id: str, speaker_id: str, transcript: str, confidence: float, detected_lang: str):
    """發送 STT 預覽給房間內的用戶"""
    try:
        from ..db.repo import UserRepo
        from ..db.pool import get_db_pool
        
        pool = await get_db_pool()
        async with pool.acquire() as db:
            user_repo = UserRepo(db)
            speaker = await user_repo.get_user(speaker_id)
            speaker_name = speaker["display_name"] if speaker else "Unknown"
        
        # 廣播 STT 預覽
        preview_message = {
            "type": "stt.preview",
            "speakerId": speaker_id,
            "speakerName": speaker_name,
            "transcript": transcript,
            "confidence": confidence,
            "detectedLang": detected_lang,
            "status": "awaiting_confirmation",
            "timestamp": None
        }
        
        await manager.broadcast_to_room(room_id, preview_message)
        
    except Exception as e:
        print(f"Error sending STT preview: {e}")

async def process_speech_translation(
    message_id: str, 
    room_id: str, 
    speaker_id: str, 
    text: str, 
    source_lang: str,
    db: asyncpg.Connection
):
    """背景處理語音翻譯和廣播（重用原有邏輯）"""
    try:
        # 取得在線使用者列表
        online_users = await manager.get_room_users(room_id)
        
        # 計算目標語言
        lang_router = LanguageRouter(db)
        target_langs = await lang_router.get_all_target_languages(room_id, speaker_id, online_users)
        
        # 批次翻譯
        translations = await translation_service.batch_translate(
            text, list(target_langs), source_lang
        )
        
        # 儲存翻譯結果
        message_repo = MessageRepo(db)
        for target_lang, translation in translations.items():
            await message_repo.save_translation(
                message_id=message_id,
                target_lang=target_lang,
                text=translation["text"],
                latency_ms=translation.get("latency_ms"),
                quality=translation.get("quality")
            )
        
        # 廣播翻譯完成訊息
        await broadcast_speech_translations(
            room_id, speaker_id, message_id, text, source_lang, 
            translations, online_users, db
        )
        
    except Exception as e:
        print(f"Error processing speech translation: {e}")

async def broadcast_speech_translations(
    room_id: str, speaker_id: str, message_id: str, original_text: str, 
    source_lang: str, translations: dict, online_users: list, db: asyncpg.Connection
):
    """廣播語音翻譯結果"""
    try:
        from ..db.repo import UserRepo
        user_repo = UserRepo(db)
        
        # 取得講者資訊
        speaker = await user_repo.get_user(speaker_id)
        speaker_name = speaker["display_name"] if speaker else "Unknown"
        
        # 計算語言路由
        lang_router = LanguageRouter(db)
        lang_sets = await lang_router.get_target_languages(room_id, speaker_id, online_users)
        
        # 廣播個人字幕給每個使用者
        for user_id in online_users:
            user = await user_repo.get_user(user_id)
            if user:
                user_lang = user["preferred_lang"]
                translated_text = translations.get(user_lang, {}).get("text", original_text)
                
                personal_message = {
                    "type": "personal.subtitle",
                    "messageId": message_id,
                    "targetLang": user_lang,
                    "text": translated_text,
                    "speakerName": speaker_name,
                    "source": "speech_staged",
                    "timestamp": None
                }
                
                await manager.send_to_user(room_id, user_id, personal_message)
        
        # 廣播主板訊息
        board_lang = list(lang_sets["board"])[0] if lang_sets["board"] else "en"
        board_text = translations.get(board_lang, {}).get("text", original_text)
        
        board_message = {
            "type": "board.post",
            "messageId": message_id,
            "speakerId": speaker_id,
            "speakerName": speaker_name,
            "targetLang": board_lang,
            "text": board_text,
            "sourceLang": source_lang,
            "source": "speech_staged",
            "timestamp": None
        }
        
        await manager.broadcast_to_room(room_id, board_message)
        
        # 發送翻譯完成通知
        completion_message = {
            "type": "translation.completed",
            "messageId": message_id,
            "translationsCount": len(translations),
            "timestamp": None
        }
        
        await manager.broadcast_to_room(room_id, completion_message)
        
    except Exception as e:
        print(f"Error broadcasting speech translations: {e}")

@router.get("/transcript/{transcript_id}")
async def get_transcript(
    transcript_id: str,
    current_user: str = Depends(get_current_user)
):
    """取得 STT 結果（用於前端查詢）"""
    if transcript_id not in transcript_cache:
        raise HTTPException(status_code=404, detail="Transcript not found or expired")
    
    stt_data = transcript_cache[transcript_id]
    
    # 驗證用戶權限
    if stt_data["user_id"] != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "transcript_id": transcript_id,
        "transcript": stt_data["transcript"],
        "confidence": stt_data["confidence"],
        "detected_lang": stt_data["detected_lang"],
        "room_id": stt_data["room_id"]
    }

@router.delete("/transcript/{transcript_id}")
async def cancel_transcript(
    transcript_id: str,
    current_user: str = Depends(get_current_user)
):
    """取消 STT 結果（不進行翻譯）"""
    if transcript_id not in transcript_cache:
        raise HTTPException(status_code=404, detail="Transcript not found or expired")
    
    stt_data = transcript_cache[transcript_id]
    
    # 驗證用戶權限
    if stt_data["user_id"] != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 清除快取
    del transcript_cache[transcript_id]
    
    return {"message": "Transcript cancelled successfully"}