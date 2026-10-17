from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from typing import Optional
from pydantic import BaseModel
import asyncpg
import re
import time
from ..deps import get_db, get_current_user
from ..db.repo import MessageRepo, RoomRepo, UserRepo
from ..services.stt import stt_service
from ..services.translate import translation_service, detect_language
from ..services.router import LanguageRouter, board_lang_for
from ..ws.hub import manager

router = APIRouter()

# Whisper 在沒人講話時常編出來的字幕（訓練資料是影片字幕）
_HALLUCINATION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"(點贊|点赞).*(訂閱|订阅)|(訂閱|订阅).*(頻道|频道|轉發|转发|打賞|打赏)|明鏡與|明镜与|點點欄目|点点栏目",
    r"字幕(由|提供|製作|制作|志願|志愿|組|组|by)|中文字幕|字幕君",
    r"^(作詞|作词|作曲|編曲|编曲|詞曲|词曲|演唱|監製|监制)\s*[:：]?\s*\S{0,8}$",
    r"(作詞|作词)\s*[:：]?\s*\S+\s+(作曲)",
    r"感謝(收看|觀看|您的觀看)|感谢(收看|观看|您的观看)|下次再[見见]|歡迎收看|欢迎收看",
    r"thank(s| you) for watching|please subscribe|like and subscribe|amara\.org|subtitles by",
    r"ご視聴ありがとうございました|チャンネル登録",
    r"MBC\s*뉴스|구독.*좋아요|좋아요.*구독|시청해\s*주셔서",
]]
# 單獨出現時很可能是幻覺，但真人也可能講；只有在「沒有語音機率」偏高時才丟
_WEAK_HALLUCINATIONS = {"you", "thank you", "thanks", "bye", "謝謝", "谢谢", "謝謝大家", "谢谢大家", "嗯", "おすすめ"}
# 同一段話連續重複 3 次以上（Whisper 卡住），只留一次
_REPEAT = re.compile(r"(.{2,}?)(?:[\s，,、]*\1){2,}")

def filter_ai_default_responses(text: str, allow_short: bool = False, no_speech_prob: float = 0.0) -> str:
    """過濾AI語音辨識模型在無聲音時的預設回應"""
    if not text or not text.strip():
        return ""

    text_cleaned = _REPEAT.sub(r"\1", text.strip())

    for pattern in _HALLUCINATION_PATTERNS:
        if pattern.search(text_cleaned):
            print(f"🔇 [STT] 過濾幻覺字串: {text_cleaned}")
            return ""

    bare = text_cleaned.strip(" 。.！!？?，,").lower()
    if bare in _WEAK_HALLUCINATIONS and no_speech_prob > 0.1:
        print(f"🔇 [STT] 過濾疑似幻覺短句: {text_cleaned} (no_speech={no_speech_prob:.2f})")
        return ""

    if re.match(r"^[\s.。，,!！?？…]*$", text_cleaned):
        return ""

    if len(text_cleaned) <= 2 and not allow_short:
        return ""

    return text_cleaned

# Whisper 自動偵測回傳的是語言全名（如 "Spanish"），轉成兩碼代碼方便比對
_WHISPER_LANG_NAMES = {
    'chinese': 'zh', 'mandarin': 'zh', 'cantonese': 'zh', 'english': 'en', 'japanese': 'ja',
    'korean': 'ko', 'spanish': 'es', 'french': 'fr', 'german': 'de', 'italian': 'it',
    'portuguese': 'pt', 'russian': 'ru', 'arabic': 'ar', 'hindi': 'hi', 'thai': 'th',
    'vietnamese': 'vi', 'indonesian': 'id', 'malay': 'ms',
}

def base_lang(code: Optional[str]) -> str:
    """'zh-TW' / 'Chinese' / 'zh' -> 'zh'"""
    if not code:
        return ''
    lower = code.strip().lower()
    return _WHISPER_LANG_NAMES.get(lower, lower.replace('_', '-').split('-')[0])

async def get_room_spoken_langs(db: asyncpg.Connection, room_id: str, speaker: Optional[dict]) -> set:
    """房間中預期會出現的語言：在線使用者與講者的慣用語 + 主板語言"""
    online_users = await manager.get_room_users(room_id)
    users_map = await UserRepo(db).get_users_batch(list(online_users)) if online_users else {}
    langs = set()
    for user in list(users_map.values()) + ([speaker] if speaker else []):
        if user:
            langs.add(base_lang(user.get("input_lang") or user.get("preferred_lang")))
    room = await RoomRepo(db).get_room(room_id)
    langs.add(base_lang((room or {}).get("default_board_lang") or "zh-TW"))
    langs.discard('')
    return langs

# ── 分段即時翻譯 ──────────────────────────────────────────────
# 前端講話中每隔幾秒就把「這個視窗從頭到現在」的音訊整段送來（is_final=False），
# 後端重新辨識並取代這個視窗的文字，所以前面聽錯的字會被後面的上下文修正。
# 視窗太長時前端在最安靜處切開、window 加一：舊視窗的文字定下來（committed），
# 新視窗接在後面。整句（utterance）共用同一則訊息，主板與手機用同一個 messageId
# 原地更新；累積的文字夠長時在句尾標點處斷開，定稿成一則、剩下的開新的一則。
_UTTERANCES: dict = {}    # (user_id, utterance_id) -> {message_id, committed, window, window_text, lang, updated}
_MSG_VERSIONS: dict = {}  # message_id -> 最新版本號，舊的翻譯結果不要蓋掉新的
_UTTERANCE_TTL = 120
_MAX_UTTERANCE_CHARS = 150  # 定下來的文字超過這個長度就算沒有標點也先定稿一則
_SPLIT_MIN_CHARS = 40       # 定下來的文字超過這個長度、又有句尾標點，就在標點處斷開
_TRAILING_PUNCT = '。．.，,、！？!?…；; '
_SENTENCE_END = re.compile(r'[。！？!?；;]|\.(?=\s)')
_NO_SPACE_LANGS = {'zh', 'ja', 'th', 'yue'}

def _prune_state():
    now = time.time()
    for key in [k for k, v in _UTTERANCES.items() if now - v["updated"] > _UTTERANCE_TTL]:
        _UTTERANCES.pop(key, None)
    if len(_MSG_VERSIONS) > 2000:
        for key in list(_MSG_VERSIONS)[:1000]:
            _MSG_VERSIONS.pop(key, None)

def join_segment(prev: str, new: str, lang: Optional[str]) -> str:
    """接上被切開的下一段；前一段結尾 Whisper 自己補的標點要拿掉"""
    sep = '' if base_lang(lang) in _NO_SPACE_LANGS else ' '
    return prev.rstrip(_TRAILING_PUNCT) + sep + new.strip()

def split_completed(text: str) -> tuple:
    """(已講完的句子, 尚未講完的部分)。句尾標點後面還有字，才算真正斷句。"""
    body = text.rstrip(_TRAILING_PUNCT)
    ends = list(_SENTENCE_END.finditer(body))
    if not ends:
        return '', text
    cut = ends[-1].end()
    return text[:cut].strip(), text[cut:].strip()

def whisper_lang(lang: Optional[str]) -> Optional[str]:
    """把已偵測到的語言（'Chinese'、'zh-TW'）轉成 Whisper 認得的兩碼，不認得就讓它自動偵測"""
    code = base_lang(lang)
    return code if code in set(_WHISPER_LANG_NAMES.values()) else None

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
    speaker_name: str = None,
    partial: bool = False,
    version: int = 0
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
            if version and _MSG_VERSIONS.get(message_id, version) != version:
                print(f"⏭️ 訊息 {message_id} 已有更新的版本，略過舊翻譯")
                return

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

            # 5. 廣播 — 一次批次查詢取代廣播迴圈中的 N 次個別查詢
            t_broadcast_start = time.time()
            all_ids = list(set(online_users) | {speaker_id})
            users_map = await UserRepo(db).get_users_batch(all_ids)
            await broadcast_speech_translations(
                room_id, speaker_id, message_id, text, source_lang,
                translations, online_users, users_map, db, speaker_name, partial
            )
            print(f"⏱️ [PERF][BG] 廣播翻譯結果耗時: {time.time() - t_broadcast_start:.3f} 秒")
            print(f"✅ process_speech_translation 完成執行 (總流程耗時: {time.time() - t_bg_full_start:.3f} 秒)")
            
    except Exception as e:
        print(f"❌ [CRITICAL] Background Task Failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

async def broadcast_speech_translations(
    room_id: str, speaker_id: str, message_id: str, original_text: str,
    source_lang: str, translations: dict, online_users: list, users_map: dict,
    db: asyncpg.Connection, speaker_name: str = None, partial: bool = False
):
    """廣播語音轉文字的翻譯結果（使用預先批次查詢的使用者資料，零額外 DB 查詢）"""
    try:
        speaker = users_map.get(speaker_id)
        if not speaker_name:
            speaker_name = speaker["display_name"] if speaker else "Unknown"

        for user_id in online_users:
            user = users_map.get(user_id)
            if user:
                user_input_lang = user.get("input_lang") or user.get("preferred_lang", "zh-TW")
                translated_text = translations.get(user_input_lang, {}).get("text", original_text)
                personal_message = {
                    "type": "personal.subtitle",
                    "messageId": message_id, "targetLang": user_input_lang,
                    "text": translated_text, "speakerName": speaker_name,
                    "sourceLang": source_lang, "source": "speech", "timestamp": None,
                    "partial": partial
                }
                await manager.send_to_user(room_id, user_id, personal_message)

        # 廣播主板
        if speaker:
            room_repo = RoomRepo(db)
            room = await room_repo.get_room(room_id)
            override = {o["speakerId"]: o["targetLang"] for o in await room_repo.get_lang_overrides(room_id)}.get(speaker_id)
            board_lang = board_lang_for(speaker, override, room)
            speaker_board_text = translations.get(board_lang, {}).get("text", original_text)
            board_message = {
                "type": "board.post",
                "messageId": message_id, "speakerId": speaker_id,
                "speakerName": speaker_name, "targetLang": board_lang,
                "text": speaker_board_text, "sourceLang": source_lang,
                "source": "speech", "timestamp": None, "partial": partial
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
    utterance_id: Optional[str] = Form(None),
    window: int = Form(0),
    is_final: bool = Form(True),
    audio: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """上傳語音檔案進行轉錄和翻譯。

    utterance_id / window / is_final 用於分段即時翻譯：is_final=False 表示這句還沒講完，
    音訊是目前視窗從頭到現在的全部內容，結果取代這個視窗上一次的文字。
    """
    try:
        room_repo = RoomRepo(db)
        if not await room_repo.get_room(room_id):
            raise HTTPException(status_code=404, detail="Room not found")

        _prune_state()
        state_key = (current_user, utterance_id) if utterance_id else None
        state = _UTTERANCES.get(state_key) if state_key else None
        if state and window != state["window"]:
            # 上一個視窗結束：它最後一次的辨識結果就是定案
            state["committed"] = join_segment(state["committed"], state["window_text"], state["lang"]) if state["committed"] else state["window_text"]
            state["window"] = window
            state["window_text"] = ""

        audio_data = await audio.read()
        # 同一句沿用已偵測到的語言；前一個視窗的文字當提示，接得更順
        stt_lang = language_code or (whisper_lang(state["lang"]) if state else None)
        prompt = state["committed"][-200:] if state and state["committed"] else None
        if audio_data:
            t_stt_start = time.time()
            stt_result = await stt_service.transcribe_audio(audio_data, audio.content_type, stt_lang, prompt)
            print(f"⏱️ [PERF][STT] Groq 語音辨識耗時: {time.time() - t_stt_start:.3f} 秒 (utterance={utterance_id}, window={window}, final={is_final}, 接續={bool(state)})")
        else:
            # 空段落：前端通知「這句講完了」，不用辨識
            stt_result = {"text": "", "confidence": 0.0, "language": None}

        # 自動偵測語言時，短句常被誤判（中文被判成西班牙文、日文）。
        # 偵測結果不是房間裡任何人的語言時，改用講者的慣用語重新辨識一次。
        if audio_data and not stt_lang:
            speaker = await UserRepo(db).get_user(current_user)
            speaker_lang = (speaker or {}).get("input_lang") or (speaker or {}).get("preferred_lang")
            detected = base_lang(stt_result.get("language"))
            room_langs = await get_room_spoken_langs(db, room_id, speaker)
            # 幾乎沒有語音時不必重試（重試只會換一種語言編字幕）
            if speaker_lang and detected and detected not in room_langs and stt_result.get("no_speech_prob", 0.0) < 0.5:
                print(f"🔁 [STT] 偵測到 {stt_result.get('language')}，不在房間語言 {room_langs} 中，改用講者慣用語 {speaker_lang} 重新辨識")
                t_retry = time.time()
                stt_result = await stt_service.transcribe_audio(audio_data, audio.content_type, speaker_lang)
                stt_result["language"] = speaker_lang
                print(f"⏱️ [PERF][STT] 重新辨識耗時: {time.time() - t_retry:.3f} 秒，結果: {stt_result.get('text', '')[:50]}")

        continuing = bool(state and state["committed"])
        transcript = filter_ai_default_responses(stt_result["text"], allow_short=continuing,
                                                 no_speech_prob=stt_result.get("no_speech_prob", 0.0))
        # Whisper 偶爾會把提示（前文）原樣吐回來
        if continuing and transcript and state["committed"].rstrip(_TRAILING_PUNCT).endswith(transcript.rstrip(_TRAILING_PUNCT)):
            transcript = ""

        if state:
            detected_lang = state["lang"]
        else:
            detected_lang = stt_result.get("language", language_code) or (detect_language(transcript) if transcript else "zh-TW")

        message_repo = MessageRepo(db)

        async def save(message_id: Optional[str], text: str, final: bool) -> str:
            if message_id:
                await message_repo.update_message_text(message_id, text, final)
            else:
                message_id = await message_repo.create_message(room_id=room_id, speaker_id=current_user, text=text, source_lang=detected_lang, is_final=final)
            version = _MSG_VERSIONS.get(message_id, 0) + 1
            _MSG_VERSIONS[message_id] = version
            print(f"🚀 啟動背景翻譯任務... message_id: {message_id} v{version} {'定稿' if final else '進行中'}: {text[:60]}")
            background_tasks.add_task(process_speech_translation, message_id, room_id, current_user, text, detected_lang, speaker_name, not final, version)
            return message_id

        if not state:
            if not transcript:
                return SpeechResponse(message_id="filtered", transcript="", confidence=0.0, detected_lang=detected_lang, status="filtered")
            message_id = await save(None, transcript, is_final)
            if state_key and not is_final:
                _UTTERANCES[state_key] = {"message_id": message_id, "committed": "", "window": window,
                                          "window_text": transcript, "lang": detected_lang, "updated": time.time()}
            return SpeechResponse(message_id=message_id, transcript=transcript, confidence=stt_result["confidence"], detected_lang=detected_lang, status="processing")

        # 接續中的一句。這次的結果取代目前視窗的文字（空的就保留上一次的）
        if transcript:
            state["window_text"] = transcript
        state["updated"] = time.time()

        # 依斷句決定顯示：定下來的文字夠長、有句尾標點就斷開，定稿成一則，剩下的開新的一則
        committed = state["committed"]
        if not is_final and committed:
            done, rest = split_completed(committed) if len(committed) >= _SPLIT_MIN_CHARS else ('', committed)
            if not done and len(committed) > _MAX_UTTERANCE_CHARS:
                done, rest = committed, ''
            if done:
                await save(state["message_id"], done, True)
                state["message_id"] = None
                state["committed"] = committed = rest

        full_text = join_segment(committed, state["window_text"], detected_lang) if committed else state["window_text"]
        if not full_text:
            if is_final:
                _UTTERANCES.pop(state_key, None)
            return SpeechResponse(message_id=state["message_id"] or "filtered", transcript="", confidence=0.0, detected_lang=detected_lang, status="filtered")

        message_id = await save(state["message_id"], full_text, is_final)
        state["message_id"] = message_id
        if is_final:
            _UTTERANCES.pop(state_key, None)

        return SpeechResponse(message_id=message_id, transcript=transcript, confidence=stt_result["confidence"], detected_lang=detected_lang, status="processing")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream-start")
async def start_speech_stream(room_id: str = Form(...), language_code: str = Form("zh-TW"), current_user: str = Depends(get_current_user), db: asyncpg.Connection = Depends(get_db)):
    return {"status": "stream_started"}

@router.post("/stream-stop")
async def stop_speech_stream(room_id: str = Form(...), current_user: str = Depends(get_current_user)):
    return {"status": "stream_stopped"}
