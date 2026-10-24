import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..deps import get_current_user
from ..services.stt import stt_service
from ..services.translate import detect_language, translation_service
from .speech import filter_ai_default_responses
from opencc import OpenCC

# Whisper 的中文常常是簡體；依使用者選的是繁中還是簡中統一字形
_TO_TRADITIONAL = OpenCC("s2tw")
_TO_SIMPLIFIED = OpenCC("t2s")
# Whisper 中文常用半形標點（「你好,歡迎」），換成全形
_ZH_PUNCT_MAP = {",": "，", "?": "？", "!": "！"}
_ZH_PUNCT = re.compile(r"(?<![0-9])([,?!])\s*")  # 1,000 這種數字不換

# 講話中的即時預覽用較快的 turbo（額度與 large-v3 分開算）；定稿用 large-v3
INTERIM_STT_MODEL = "whisper-large-v3-turbo"


router = APIRouter()


class TranslatorResponse(BaseModel):
    transcript: str
    translated_text: str
    detected_lang: str
    source_lang: str
    target_lang: str
    confidence: float
    # ok：有翻譯；empty：沒人講話或被當成雜訊；other_lang：講的不是選的兩種語言（旁邊的人）
    status: str = "ok"


# These are the language families the two-way mode can match reliably.  The
# UI exposes a smaller subset, but accepting common provider/name variants here
# keeps the API compatible with STT providers that return names such as
# "Chinese" or regional codes such as "zh-TW".
_LANGUAGE_ALIASES = {
    "chinese": "zh",
    "mandarin": "zh",
    "cantonese": "zh",
    "traditional chinese": "zh",
    "simplified chinese": "zh",
    "malay": "ms",
    "bahasa melayu": "ms",
    "english": "en",
    "thai": "th",
    "vietnamese": "vi",
    "indonesian": "id",
    "japanese": "ja",
    "korean": "ko",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "arabic": "ar",
    "hindi": "hi",
    "dutch": "nl",
    "turkish": "tr",
}


def _normalize_lang(code: Optional[str]) -> str:
    if not code:
        return ""
    value = code.strip().lower().replace("_", "-")
    if value in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[value]
    return value.split("-", 1)[0]


def _language_family(code: Optional[str]) -> str:
    """Return a comparable family code while retaining selected region codes elsewhere."""
    return _normalize_lang(code)


def _selected_lang(code: str) -> str:
    """Normalize a requested target without losing Traditional Chinese."""
    value = code.strip().replace("_", "-")
    lower = value.lower()
    if lower in {"zh-tw", "zh-hk"}:
        return "zh-TW"
    if lower in {"zh-cn", "zh-sg", "zh"}:
        return "zh-CN" if lower != "zh" else "zh"
    return _normalize_lang(value)


def _language_matches(detected: str, selected: str) -> bool:
    return _language_family(detected) == _language_family(selected)


def _empty(status: str = "empty") -> TranslatorResponse:
    # 連續收音時常會送出只有雜音或停頓的片段，屬於正常情況，不能變成錯誤訊息
    return TranslatorResponse(
        transcript="", translated_text="", detected_lang="", source_lang="",
        target_lang="", confidence=0.0, status=status,
    )


@router.post("/translate", response_model=TranslatorResponse)
async def translate_audio(
    audio: UploadFile = File(...),
    lang_a: str = Form(...),
    lang_b: str = Form(...),
    is_final: bool = Form(True),
    current_user: str = Depends(get_current_user),
):
    """Transcribe one recording and translate it between the two selected languages.

    is_final=False 是講話中的即時預覽：用較快的模型，結果之後會被定稿取代。
    """
    # current_user intentionally only verifies the existing JWT.  This endpoint
    # does not load a user, room, or database connection.
    _ = current_user
    if not lang_a.strip() or not lang_b.strip():
        raise HTTPException(status_code=400, detail="lang_a and lang_b are required")

    selected_a = _selected_lang(lang_a)
    selected_b = _selected_lang(lang_b)
    if not selected_a or not selected_b:
        raise HTTPException(status_code=400, detail="Both languages must be valid language codes")
    if _language_family(selected_a) == _language_family(selected_b):
        raise HTTPException(status_code=400, detail="lang_a and lang_b must be different languages")

    audio_data = await audio.read()
    if not audio_data:
        return _empty()

    # 語言傳 None：讓 Whisper 自己判斷是兩種語言的哪一種（指定語言會把另一種語言硬翻過去）
    stt_result = await stt_service.transcribe_audio(
        audio_data,
        audio.content_type or "audio/webm",
        None,
        None,
        None if is_final else INTERIM_STT_MODEL,
    )
    if stt_result.get("rate_limited"):
        raise HTTPException(status_code=429, detail="Speech recognition rate limit reached")

    no_speech = float(stt_result.get("no_speech_prob") or 0.0)
    transcript = filter_ai_default_responses(
        (stt_result.get("text") or "").strip(), allow_short=True, no_speech_prob=no_speech
    )
    if not transcript:
        return _empty()

    detected_raw = stt_result.get("language") or detect_language(transcript)
    detected_lang = _normalize_lang(detected_raw)

    if _language_matches(detected_lang, selected_a):
        source_lang, target_lang = selected_a, selected_b
    elif _language_matches(detected_lang, selected_b):
        source_lang, target_lang = selected_b, selected_a
    else:
        # 展場旁邊的人講別的語言，或雜音被認成別的語言：安靜略過
        print(f"🔇 [Translator] 略過非選定語言 {detected_raw}: {transcript[:40]}")
        return _empty("other_lang")

    if _language_family(source_lang) == "zh":
        converter = _TO_TRADITIONAL if source_lang == "zh-TW" else _TO_SIMPLIFIED
        transcript = _ZH_PUNCT.sub(lambda m: _ZH_PUNCT_MAP[m.group(1)], converter.convert(transcript))

    translation = await translation_service.translate_text(
        transcript,
        target_lang,
        source_lang,
        fast=not is_final,
    )
    if translation.get("error"):
        raise HTTPException(status_code=502, detail="Translation service failed")

    return TranslatorResponse(
        transcript=transcript,
        translated_text=translation.get("text") or "",
        detected_lang=detected_lang,
        source_lang=source_lang,
        target_lang=target_lang,
        confidence=float(stt_result.get("confidence") or 0.0),
    )
