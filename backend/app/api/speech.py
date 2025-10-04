from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from pydantic import BaseModel
import asyncpg
from ..deps import get_db, get_current_user
from ..db.repo import MessageRepo, RoomRepo
from ..services.stt import stt_service
from ..services.translate import translation_service, detect_language
from ..services.router import LanguageRouter
from ..ws.hub import manager

router = APIRouter()

class SpeechResponse(BaseModel):
    message_id: str
    transcript: str
    confidence: float
    detected_lang: str
    status: str

async def process_speech_translation(
    message_id: str, 
    room_id: str, 
    speaker_id: str, 
    text: str, 
    source_lang: str,
    db: asyncpg.Connection
):
    """背景處理語音轉文字的翻譯和廣播"""
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
        
        # 廣播給個人視圖和主板視圖
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
    """廣播語音轉文字的翻譯結果"""
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
                    "source": "speech",
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
            "source": "speech",
            "timestamp": None
        }
        
        await manager.broadcast_to_room(room_id, board_message)
        
    except Exception as e:
        print(f"Error broadcasting speech translations: {e}")

@router.post("/upload", response_model=SpeechResponse)
async def upload_speech(
    background_tasks: BackgroundTasks,
    room_id: str = Form(...),
    language_code: str = Form("zh-TW"),
    audio: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """上傳語音檔案進行轉錄和翻譯"""
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
        
        if not transcript:
            raise HTTPException(status_code=400, detail="Could not transcribe audio")
        
        # 如果轉錄結果信心度太低，警告但仍然處理
        if confidence < 0.7:
            print(f"⚠️  Low confidence transcription: {confidence}")
        
        # 語言檢測（如果 STT 沒有提供）
        if not detected_lang or detected_lang == language_code:
            detected_lang = detect_language(transcript)
        
        # 建立訊息記錄
        message_repo = MessageRepo(db)
        message_id = await message_repo.create_message(
            room_id=room_id,
            speaker_id=current_user,
            text=transcript,
            source_lang=detected_lang,
            is_final=True
        )
        
        # 在背景處理翻譯
        background_tasks.add_task(
            process_speech_translation,
            message_id, room_id, current_user, 
            transcript, detected_lang, db
        )
        
        return SpeechResponse(
            message_id=message_id,
            transcript=transcript,
            confidence=confidence,
            detected_lang=detected_lang,
            status="processing"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process speech: {str(e)}")

@router.post("/stream-start")
async def start_speech_stream(
    room_id: str = Form(...),
    language_code: str = Form("zh-TW"),
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """開始語音串流轉錄（預留給即時 STT）"""
    try:
        # 檢查房間是否存在
        room_repo = RoomRepo(db)
        room = await room_repo.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # 這裡可以實作即時語音串流處理
        # 目前回傳成功狀態
        return {
            "status": "stream_started",
            "room_id": room_id,
            "language_code": language_code,
            "message": "Speech streaming started (feature in development)"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start speech stream: {str(e)}")

@router.post("/stream-stop")
async def stop_speech_stream(
    room_id: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """停止語音串流轉錄"""
    return {
        "status": "stream_stopped",
        "room_id": room_id,
        "message": "Speech streaming stopped"
    }