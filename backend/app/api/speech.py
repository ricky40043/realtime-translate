from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
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
        
        # 明鏡相關 - 簡體  
        "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
        "谢谢大家",
        "明镜与点点栏目",
        
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
    
    # 定義需要過濾的模糊匹配模式
    filter_patterns = [
        # 包含明鏡相關關鍵字的句子
        r".*點贊.*訂閱.*轉發.*打賞.*明鏡.*",
        r".*点赞.*订阅.*转发.*打赏.*明镜.*",
        r".*支持.*明鏡.*點點.*欄目.*",
        r".*支持.*明镜.*点点.*栏目.*",
        
        # 其他常見的AI預設回應
        r".*字幕.*製作.*",
        r".*字幕.*制作.*",
        r".*影片.*結束.*",
        r".*影片.*结束.*",
        r"^\.+$",  # 只有句號
        r"^，+$",  # 只有逗號
        r"^。+$",  # 只有句號（中文）
        r"^\s*$",  # 只有空白
        
        # 常見的無意義單字輸出
        r"^你$",
        r"^好$", 
        r"^嗯$",
        r"^啊$",
        r"^呃$",
        r"^這個$",
        r"^那個$",
        r"^这个$",
        r"^那个$",
    ]
    
    # 檢查是否匹配任何過濾模式
    for pattern in filter_patterns:
        if re.match(pattern, text_cleaned, re.IGNORECASE):
            print(f"🚫 模式匹配過濾: '{text_cleaned}' (匹配模式: {pattern})")
            return ""
    
    # 檢查長度過短的回應（少於3個字符的可能是無意義輸出）
    if len(text_cleaned) <= 2:
        print(f"🚫 過濾過短回應: '{text_cleaned}'")
        return ""
    
    # 檢查是否全是重複字符
    if len(set(text_cleaned)) <= 1:
        print(f"🚫 過濾重複字符: '{text_cleaned}'")
        return ""
        
    print(f"✅ 通過過濾檢查: '{text_cleaned}'")
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
    print(f"🔄 process_speech_translation 開始執行...")
    print(f"   message_id: {message_id}")
    print(f"   room_id: {room_id}")
    print(f"   speaker_id: {speaker_id}")
    print(f"   text: {text}")
    print(f"   source_lang: {source_lang}")
    
    # ✅ 重要：從連接池獲取新的資料庫連接
    from ..db.pool import get_db_pool
    pool = await get_db_pool()
    
    async with pool.acquire() as db:
        try:
            # 取得在線使用者列表
            online_users = await manager.get_room_users(room_id)
            print(f"   在線用戶數: {len(online_users)}")
            
            # 計算目標語言
            lang_router = LanguageRouter(db)
            target_langs = await lang_router.get_all_target_languages(room_id, speaker_id, online_users)
            print(f"   目標語言: {target_langs}")
            
            # 批次翻譯
            translations = await translation_service.batch_translate(
                text, list(target_langs), source_lang
            )
            
            print(f"🔄 翻譯結果:")
            for lang, result in translations.items():
                print(f"   {lang}: {result['text']}")
            
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
                translations, online_users, db, speaker_name
            )
            
            print(f"✅ process_speech_translation 完成執行")
            
        except Exception as e:
            print(f"❌ Error processing speech translation: {e}")
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
        
        # 優先使用傳入的speaker_name，否則從資料庫取得
        if not speaker_name:
            speaker = await user_repo.get_user(speaker_id)
            speaker_name = speaker["display_name"] if speaker else "Unknown"
        
        print(f"📝 使用講者名稱: '{speaker_name}'（來源: {'前端' if speaker_name else '資料庫'}）")
        
        # 計算語言路由
        lang_router = LanguageRouter(db)
        lang_sets = await lang_router.get_target_languages(room_id, speaker_id, online_users)
        
        # 廣播個人字幕給每個使用者（根據每個人的輸入語言/慣用語）
        for user_id in online_users:
            user = await user_repo.get_user(user_id)
            if user:
                # 用戶的慣用語（輸入語言）
                user_input_lang = user["input_lang"] if user.get("input_lang") else user["preferred_lang"]
                translated_text = translations.get(user_input_lang, {}).get("text", original_text)
                
                print(f"📤 發送個人字幕:")
                print(f"   用戶: {user_id[:8]}...")
                print(f"   慣用語: {user_input_lang}")
                print(f"   翻譯文字: {translated_text}")
                
                personal_message = {
                    "type": "personal.subtitle",
                    "messageId": message_id,
                    "targetLang": user_input_lang,
                    "text": translated_text,
                    "speakerName": speaker_name,
                    "sourceLang": source_lang,
                    "source": "speech",
                    "timestamp": None
                }
                
                await manager.send_to_user(room_id, user_id, personal_message)
        
        # 廣播主板訊息：顯示講者的輸出語言版本（講者想讓主板顯示的語言）
        speaker = await user_repo.get_user(speaker_id)
        if speaker:
            # 講者想讓主板顯示的語言版本（輸出語言）
            speaker_output_lang = speaker["output_lang"] if speaker.get("output_lang") else speaker["preferred_lang"]
            speaker_board_text = translations.get(speaker_output_lang, {}).get("text", original_text)
            
            print(f"📢 主板訊息廣播:")
            print(f"   講者輸出語言: {speaker_output_lang}")
            print(f"   主板顯示文字: {speaker_board_text}")
            
            board_message = {
                "type": "board.post",
                "messageId": message_id,
                "speakerId": speaker_id,
                "speakerName": speaker_name,  # 使用傳入的speaker_name而不是資料庫的display_name
                "targetLang": speaker_output_lang,
                "text": speaker_board_text,
                "sourceLang": source_lang,
                "source": "speech",
                "timestamp": None
            }
            
            # 廣播給房間內所有用戶（相同內容）
            await manager.broadcast_to_room(room_id, board_message)
        
    except Exception as e:
        print(f"Error broadcasting speech translations: {e}")

@router.post("/upload", response_model=SpeechResponse)
async def upload_speech(
    background_tasks: BackgroundTasks,
    room_id: str = Form(...),
    language_code: str = Form("zh-TW"),
    speaker_name: str = Form(None),
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
        
        # 過濾AI語音辨識模型的預設回應
        print(f"🔍 原始辨識結果: '{transcript}'")
        transcript = filter_ai_default_responses(transcript)
        print(f"🔍 過濾後結果: '{transcript}'")
        
        if not transcript:
            print(f"⚠️ 辨識結果被過濾或為空，跳過翻譯和Socket發送")
            # 回傳成功但不進行任何翻譯或WebSocket處理
            return SpeechResponse(
                message_id="filtered",
                transcript="",
                confidence=0.0,
                detected_lang=detected_lang,
                status="filtered"
            )
        
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
        print(f"🚀 啟動背景翻譯任務...")
        print(f"   message_id: {message_id}")
        print(f"   room_id: {room_id}")
        print(f"   speaker_id: {current_user}")
        print(f"   transcript: {transcript}")
        print(f"   detected_lang: {detected_lang}")
        
        # ✅ 不傳遞 db 連接，讓背景任務自己獲取新連接
        background_tasks.add_task(
            process_speech_translation,
            message_id, room_id, current_user, 
            transcript, detected_lang, speaker_name
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