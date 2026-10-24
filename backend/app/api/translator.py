from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..deps import get_current_user
from ..services.stt import stt_service
from ..services.translate import detect_language, translation_service


router = APIRouter()


class TranslatorResponse(BaseModel):
    transcript: str
    translated_text: str
    detected_lang: str
    source_lang: str
    target_lang: str
    confidence: float


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
    "japanese": "ja",
    "korean": "ko",
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


@router.post("/translate", response_model=TranslatorResponse)
async def translate_audio(
    audio: UploadFile = File(...),
    lang_a: str = Form(...),
    lang_b: str = Form(...),
    current_user: str = Depends(get_current_user),
):
    """Transcribe one recording and translate it between the two selected languages."""
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
        raise HTTPException(status_code=400, detail="The uploaded audio is empty")

    # Passing None is important: the STT provider must detect the spoken
    # language instead of being told which side of the pair to expect.
    stt_result = await stt_service.transcribe_audio(
        audio_data,
        audio.content_type or "audio/webm",
        None,
    )
    transcript = (stt_result.get("text") or "").strip()
    if not transcript:
        detail = stt_result.get("error") or "No speech was detected in the recording"
        raise HTTPException(status_code=422, detail=detail)

    detected_raw = stt_result.get("language") or detect_language(transcript)
    detected_lang = _normalize_lang(detected_raw)
    if not detected_lang:
        raise HTTPException(status_code=422, detail="The spoken language could not be detected")

    if _language_matches(detected_lang, selected_a):
        source_lang, target_lang = selected_a, selected_b
    elif _language_matches(detected_lang, selected_b):
        source_lang, target_lang = selected_b, selected_a
    else:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Detected language '{detected_raw}' is not one of the selected languages "
                f"('{lang_a}' or '{lang_b}')"
            ),
        )

    translation = await translation_service.translate_text(
        transcript,
        target_lang,
        source_lang,
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
