from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
import asyncpg
from ..deps import get_db, get_current_user
from ..db.repo import MessageRepo, RoomRepo
from ..services.translate import translation_service, detect_language
from ..services.router import LanguageRouter
from ..ws.hub import manager

router = APIRouter()

class IngestTextRequest(BaseModel):
    room_id: str
    text: str
    source_lang: str = None
    is_final: bool = True

class IngestResponse(BaseModel):
    message_id: str
    source_lang: str
    status: str

async def process_message_translation(
    message_id: str, 
    room_id: str, 
    speaker_id: str, 
    text: str, 
    source_lang: str
):
    """背景處理訊息翻譯和廣播"""
    print(f"🔄 process_message_translation 開始執行...")
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
            await broadcast_translations(
                room_id, speaker_id, message_id, text, source_lang, 
                translations, online_users, db
            )
            
            print(f"✅ process_message_translation 完成執行")
            
        except Exception as e:
            print(f"❌ Error processing message translation: {e}")
            import traceback
            traceback.print_exc()

async def broadcast_translations(
    room_id: str, speaker_id: str, message_id: str, original_text: str, 
    source_lang: str, translations: dict, online_users: list, db: asyncpg.Connection
):
    """廣播翻譯結果"""
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
                    "timestamp": None  # 會在 manager 中設定
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
            "timestamp": None  # 會在 manager 中設定
        }
        
        await manager.broadcast_to_room(room_id, board_message)
        
    except Exception as e:
        print(f"Error broadcasting translations: {e}")

@router.post("/text", response_model=IngestResponse)
async def ingest_text(
    request: IngestTextRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """攝取文字訊息並觸發翻譯流程"""
    try:
        # 檢查房間是否存在
        room_repo = RoomRepo(db)
        room = await room_repo.get_room(request.room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # 偵測語言（如果未指定）
        source_lang = request.source_lang
        if not source_lang:
            source_lang = detect_language(request.text)
        
        # 建立訊息記錄
        message_repo = MessageRepo(db)
        message_id = await message_repo.create_message(
            room_id=request.room_id,
            speaker_id=current_user,
            text=request.text,
            source_lang=source_lang,
            is_final=request.is_final
        )
        
        # 只有最終稿才進行翻譯和廣播
        if request.is_final:
            # 在背景處理翻譯
            # ✅ 不傳遞 db 連接，讓背景任務自己獲取新連接
            background_tasks.add_task(
                process_message_translation,
                message_id, request.room_id, current_user, 
                request.text, source_lang
            )
        
        return IngestResponse(
            message_id=message_id,
            source_lang=source_lang,
            status="processing" if request.is_final else "partial"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest text: {str(e)}")