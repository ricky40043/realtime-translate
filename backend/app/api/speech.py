from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from typing import Optional
from pydantic import BaseModel
import asyncpg
import re
import time
from ..deps import get_db, get_current_user
from ..db.repo import MessageRepo, RoomRepo
from ..services.stt import stt_service
from ..services.translate import translation_service, detect_language
from ..services.router import LanguageRouter
from ..ws.hub import manager

router = APIRouter()

def filter_ai_default_responses(text: str) -> str:
    """過濾AI語音辨識模型在無聲音時的預設回應"""
    if not text or not text.strip():
        return ""
    
    text_cleaned = text.strip()
    
    exact_filter_list = [
        "請不吝點贊 訂閱 轉發 打賞支持明鏡與點點欄目",
        "謝謝大家", "明鏡與點點欄目", "歡迎訂閱我的頻道",
        "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
        "谢谢大家", "明镜与点点栏目", "欢迎订阅我的频道",
        "感謝收看", "感谢收看", "下次再見", "下次再见"
    ]
    
    for filter_text in exact_filter_list:
        if text_cleaned == filter_text:
            return ""
    
    filter_patterns = [
        r".*點贊.*訂閱.*轉發.*打賞.*明鏡.*",
        r".*点赞.*订阅.*转发.*打赏.*明镜.*",
        r".*支持.*明鏡.*點點.*欄目.*",
        r".*支持.*明镜.*点点.*栏目.*",
        r".*字幕.*製作.*", r".*字幕.*制作.*",
        r"^\.+$", r"^，+$", r"^。+$", r"^\s*$"
    ]
    
    for pattern in filter_patterns:
        if re.match(pattern, text_cleaned, re.IGNORECASE):
            return ""
            
    if len(text_cleaned) <= 2:
        return ""
        
    return text_cleaned

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
    speaker_name: str = None
):
    """背景處理語音轉文字的翻譯和廣播"""
    t_bg_full_start = time.time()
    print(f"DEBUG: [!!!!] Background task triggered for message_id: {message_id}")
    
    try:
        print(f"🔄 process_speech_translation 開始執行...")
        print(f"   text: {text[:50]}...")
        
        # 1. 獲取連接池
        from ..db.pool import get_db_pool
        t_pool_start = time.time()
        pool = await get_db_pool()
        print(f"⏱️ [PERF][BG] 獲取 DB Pool 耗時: {time.time() - t_pool_start:.3f} 秒")
        
        async with pool.acquire() as db:
            # 2. 取得在線使用者與計算路由
            online_users = await manager.get_room_users(room_id)
            t_router_start = time.time()
            lang_router = LanguageRouter(db)
            target_langs = await lang_router.get_all_target_languages(room_id, speaker_id, online_users)
            print(f"⏱️ [PERF][BG] 語言路由計算耗時: {time.time() - t_router_start:.3f} 秒")
            print(f"   目標語言列表: {target_langs}")
            
            # 3. 批次翻譯
            t_trans_start = time.time()
            translations = await translation_service.batch_translate(
                text, list(target_langs), source_lang
            )
            print(f"⏱️ [PERF][Translate] 批次翻譯 {len(target_langs)} 種語言耗時: {time.time() - t_trans_start:.3f} 秒")
            
            # 4. 儲存結果
            message_repo = MessageRepo(db)
            for target_lang, translation in translations.items():
                await message_repo.save_translation(
                    message_id=message_id,
                    target_lang=target_lang,
                    text=translation["text"],
                    latency_ms=translation.get("latency_ms"),
                    quality=translation.get("quality")
                )
            
            # 5. 廣播
            t_broadcast_start = time.time()
            await broadcast_speech_translations(
                room_id, speaker_id, message_id, text, source_lang, 
                translations, online_users, db, speaker_name
            )
            print(f"⏱️ [PERF][BG] 廣播翻譯結果耗時: {time.time() - t_broadcast_start:.3f} 秒")
            print(f"✅ process_speech_translation 完成執行 (總流程耗時: {time.time() - t_bg_full_start:.3f} 秒)")
            
    except Exception as e:
        print(f"❌ [CRITICAL] Background Task Failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

async def broadcast_speech_translations(
    room_id: str, speaker_id: str, message_id: str, original_text: str, 
    source_lang: str, translations: dict, online_users: list, db: asyncpg.Connection,
    speaker_name: str = None
):
    """廣播語音轉文字的翻譯結果"""
    try:
        from ..db.repo import UserRepo
        user_repo = UserRepo(db)
        if not speaker_name:
            speaker = await user_repo.get_user(speaker_id)
            speaker_name = speaker["display_name"] if speaker else "Unknown"
        
        for user_id in online_users:
            user = await user_repo.get_user(user_id)
            if user:
                user_input_lang = user["input_lang"] if user.get("input_lang") else user["preferred_lang"]
                translated_text = translations.get(user_input_lang, {}).get("text", original_text)
                
                personal_message = {
                    "type": "personal.subtitle",
                    "messageId": message_id, "targetLang": user_input_lang,
                    "text": translated_text, "speakerName": speaker_name,
                    "sourceLang": source_lang, "source": "speech", "timestamp": None
                }
                await manager.send_to_user(room_id, user_id, personal_message)
        
        # 廣播主板
        speaker = await user_repo.get_user(speaker_id)
        if speaker:
            speaker_output_lang = speaker["output_lang"] if speaker.get("output_lang") else speaker["preferred_lang"]
            speaker_board_text = translations.get(speaker_output_lang, {}).get("text", original_text)
            board_message = {
                "type": "board.post",
                "messageId": message_id, "speakerId": speaker_id,
                "speakerName": speaker_name, "targetLang": speaker_output_lang,
                "text": speaker_board_text, "sourceLang": source_lang,
                "source": "speech", "timestamp": None
            }
            await manager.broadcast_to_room(room_id, board_message)
    except Exception as e:
        print(f"Error broadcasting speech translations: {e}")

@router.post("/upload", response_model=SpeechResponse)
async def upload_speech(
    background_tasks: BackgroundTasks,
    room_id: str = Form(...),
    language_code: Optional[str] = Form(None),
    speaker_name: Optional[str] = Form(None),
    audio: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """上傳語音檔案進行轉錄和翻譯"""
    try:
        room_repo = RoomRepo(db)
        if not await room_repo.get_room(room_id):
            raise HTTPException(status_code=404, detail="Room not found")
        
        audio_data = await audio.read()
        t_stt_start = time.time()
        stt_result = await stt_service.transcribe_audio(audio_data, audio.content_type, language_code)
        print(f"⏱️ [PERF][STT] Groq 語音辨識耗時: {time.time() - t_stt_start:.3f} 秒")
        
        transcript = filter_ai_default_responses(stt_result["text"])
        if not transcript:
            return SpeechResponse(message_id="filtered", transcript="", confidence=0.0, detected_lang="zh-TW", status="filtered")
        
        detected_lang = stt_result.get("language", language_code) or detect_language(transcript)
        message_repo = MessageRepo(db)
        message_id = await message_repo.create_message(room_id=room_id, speaker_id=current_user, text=transcript, source_lang=detected_lang, is_final=True)
        
        print(f"🚀 啟動背景翻譯任務... message_id: {message_id}")
        background_tasks.add_task(process_speech_translation, message_id, room_id, current_user, transcript, detected_lang, speaker_name)
        
        return SpeechResponse(message_id=message_id, transcript=transcript, confidence=stt_result["confidence"], detected_lang=detected_lang, status="processing")
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream-start")
async def start_speech_stream(room_id: str = Form(...), language_code: str = Form("zh-TW"), current_user: str = Depends(get_current_user), db: asyncpg.Connection = Depends(get_db)):
    return {"status": "stream_started"}

@router.post("/stream-stop")
async def stop_speech_stream(room_id: str = Form(...), current_user: str = Depends(get_current_user)):
    return {"status": "stream_stopped"}
