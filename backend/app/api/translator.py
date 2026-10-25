import asyncio
import re
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..deps import get_current_user
from ..services.stt import stt_service
from ..services.translate import detect_language, translation_service
from ..services import groq_quota
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


class TranslatorSegment(BaseModel):
    transcript: str
    translated_text: str
    source_lang: str
    target_lang: str


class TranslatorResponse(BaseModel):
    transcript: str
    translated_text: str
    detected_lang: str
    source_lang: str
    target_lang: str
    confidence: float
    # ok：有翻譯；empty：沒人講話或被當成雜訊；other_lang：講的不是選的兩種語言（旁邊的人）
    status: str = "ok"
    # Groq 剩餘次數（從這次呼叫的回應標頭記下來的，不另外打 API），畫面右上角跟著更新
    quota: Optional[dict] = None
    # 一段話裡其實是兩個人接著講（不同語言）時拆開的結果；第一段同時放在上面的欄位
    segments: Optional[List[TranslatorSegment]] = None
    server_ms: Optional[int] = None


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


_MALAY_INDONESIAN = {"ms", "id"}


# 各語言用的文字；兩邊文字不同時（例如中文 vs 英文），可以從字數判斷一句夾雜的話主要是哪一種
_SCRIPT_OF_FAMILY = {
    "zh": "han", "ja": "kana", "ko": "hangul", "th": "thai", "ar": "arabic",
    "ru": "cyrillic", "hi": "devanagari",
}
_SCRIPT_PATTERNS = {
    "han": re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]"),
    "kana": re.compile(r"[\u3040-\u30ff]"),
    "hangul": re.compile(r"[\uac00-\ud7af]"),
    "thai": re.compile(r"[\u0e00-\u0e7f]"),
    "arabic": re.compile(r"[\u0600-\u06ff]"),
    "cyrillic": re.compile(r"[\u0400-\u04ff]+"),
    "devanagari": re.compile(r"[\u0900-\u097f]+"),
    "latin": re.compile(r"[A-Za-z\u00c0-\u024f]+(?:'[A-Za-z]+)?"),
}
# 一個英文單字大約等於 1.5 個中文字的份量
_SCRIPT_WEIGHT = {"latin": 1.5, "cyrillic": 1.5, "devanagari": 1.5}


def _script_of(code: str) -> str:
    return _SCRIPT_OF_FAMILY.get(_language_family(code), "latin")


def _dominant_side(text: str, side_a: list, side_b: list) -> Optional[int]:
    """一句話同時有兩邊的文字（中英夾雜、對方插話）時，回傳份量比較多的那一邊（0=A、1=B）；
    沒有夾雜或兩邊用同一種文字（例如英文 vs 馬來文）就回傳 None，交給語音辨識的判斷"""
    scripts_a = {_script_of(c) for c in side_a}
    scripts_b = {_script_of(c) for c in side_b}
    if scripts_a & scripts_b:
        return None

    def amount(scripts):
        return sum(len(_SCRIPT_PATTERNS[sc].findall(text)) * _SCRIPT_WEIGHT.get(sc, 1.0) for sc in scripts)

    a, b = amount(scripts_a), amount(scripts_b)
    if not a or not b:
        return None
    return 0 if a >= b else 1


# 夾雜的一段要多大才算「另一個人講的一句」：約 4 個中文字或 3 個英文單字；
# 更小的（「I think 這個 is great」裡的「這個」）當成同一個人順口夾雜
_MIN_SPLIT_AMOUNT = 4
_TOKEN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f\u0600-\u06ff]"
                    r"|[\u0400-\u04ff]+|[\u0900-\u097f]+|[A-Za-z\u00c0-\u024f]+(?:'[A-Za-z]+)?|.", re.S)


def _split_mixed(text: str, side_a: list, side_b: list) -> Optional[list]:
    """一段話裡有兩邊各自成句的內容（對方插話、兩人接著講沒有停頓），
    拆成 [(文字, 0=A/1=B), ...]；沒有夾雜或只是順口夾幾個字就回傳 None"""
    scripts = ({_script_of(c) for c in side_a}, {_script_of(c) for c in side_b})
    if scripts[0] & scripts[1]:
        return None
    runs = []  # [文字, 哪一邊, 份量]
    for token in _TOKEN.findall(text):
        side = None
        for sc, pattern in _SCRIPT_PATTERNS.items():
            if pattern.fullmatch(token):
                side = 0 if sc in scripts[0] else 1 if sc in scripts[1] else None
                weight = _SCRIPT_WEIGHT.get(sc, 1.0)
                break
        if side is None or not runs or runs[-1][1] != side:
            if side is None:
                if runs:
                    runs[-1][0] += token  # 標點、空白、數字跟著前面那段
                else:
                    runs.append([token, None, 0.0])
                continue
            runs.append([token, side, weight])
        else:
            runs[-1][0] += token
            runs[-1][2] += weight
    # 太小段的併進前一段（開頭的併進下一段）
    merged = []
    for run in runs:
        if merged and (run[2] < _MIN_SPLIT_AMOUNT or run[1] is None or merged[-1][1] is None):
            merged[-1][0] += run[0]
            if merged[-1][1] is None:
                merged[-1][1], merged[-1][2] = run[1], run[2]
            continue
        if merged and merged[-1][2] < _MIN_SPLIT_AMOUNT and len(merged) == 1:
            run = [merged.pop()[0] + run[0], run[1], run[2]]
        if merged and merged[-1][1] == run[1]:
            merged[-1][0] += run[0]
            merged[-1][2] += run[2]
        else:
            merged.append(run)
    parts = [(t.strip(), side) for t, side, _ in merged if t.strip() and side is not None]
    return parts if len(parts) > 1 else None


def _normalize_lang(code: Optional[str]) -> str:
    if not code:
        return ""
    # Whisper 回傳的是語言名稱，有的帶括號，例如 "Malay (macrolanguage)"
    value = re.sub(r"\s*\(.*\)$", "", code.strip().lower()).replace("_", "-")
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


def _any_matches(detected: str, side: list) -> bool:
    return any(_language_matches(detected, c) for c in side)


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
    started = time.perf_counter()
    response = await _translate_audio(audio, lang_a, lang_b, is_final, current_user)
    response.quota = groq_quota.cached()
    # 伺服器處理花的時間：前端用「來回時間 − 這個」算出網路上傳速度，決定要不要壓縮
    response.server_ms = int((time.perf_counter() - started) * 1000)
    return response


@router.post("/ping")
async def ping(request: Request, current_user: str = Depends(get_current_user)):
    """測網速用：收下一段資料就回傳，不呼叫任何模型、不用額度"""
    _ = current_user
    body = await request.body()
    return {"bytes": len(body)}


async def _translate_audio(audio: UploadFile, lang_a: str, lang_b: str, is_final: bool, current_user: str) -> TranslatorResponse:
    """Transcribe one recording and translate it between the two selected languages.

    is_final=False 是講話中的即時預覽：用較快的模型，結果之後會被定稿取代。
    """
    # current_user intentionally only verifies the existing JWT.  This endpoint
    # does not load a user, room, or database connection.
    _ = current_user
    # 每一邊可以多選（逗號分隔，例如 lang_a="zh-TW,en"、lang_b="ms"）：
    # 講 A 邊任一種語言 → 翻成 B 邊的第一個；講 B 邊任一種 → 翻成 A 邊的第一個
    side_a = [_selected_lang(c) for c in lang_a.split(",") if c.strip()]
    side_b = [_selected_lang(c) for c in lang_b.split(",") if c.strip()]
    if not side_a or not side_b:
        raise HTTPException(status_code=400, detail="lang_a and lang_b are required")
    if not all(side_a + side_b):
        raise HTTPException(status_code=400, detail="Both languages must be valid language codes")
    families_a = {_language_family(c) for c in side_a}
    families_b = {_language_family(c) for c in side_b}
    if families_a & families_b:
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

    known = _any_matches(detected_lang, side_a) or _any_matches(detected_lang, side_b)
    parts = _split_mixed(transcript, side_a, side_b) if known and is_final else None
    if parts:
        # 兩個人的話接在一起（插話、沒有停頓）：拆開各自翻給對方，畫面上變成兩個對話框
        sides = (side_a, side_b)
        jobs = []
        for text, side in parts:
            own, other = sides[side], sides[1 - side]
            jobs.append((_pick_source(own, text, detected_lang), other[0], text))
        done = await asyncio.gather(*[_translate_part(t, src, tgt, is_final) for src, tgt, t in jobs])
        segments = [
            TranslatorSegment(transcript=tr, translated_text=tx, source_lang=src, target_lang=tgt)
            for (src, tgt, _), (tr, tx) in zip(jobs, done)
        ]
        print(f"✂️ [Translator] 拆成 {len(segments)} 段: {[s.transcript[:20] for s in segments]}")
        first = segments[0]
        return TranslatorResponse(
            transcript=first.transcript, translated_text=first.translated_text,
            detected_lang=detected_lang, source_lang=first.source_lang, target_lang=first.target_lang,
            confidence=float(stt_result.get("confidence") or 0.0), segments=segments,
        )

    source_lang = target_lang = ""
    dominant = _dominant_side(transcript, side_a, side_b)
    if dominant is not None and known:
        # 夾雜的話：照主要的文字決定方向，整句翻成另一邊的主要語言
        own, other = (side_a, side_b) if dominant == 0 else (side_b, side_a)
        source_lang = _pick_source(own, transcript, detected_lang)
        target_lang = other[0]
        if not _any_matches(detected_lang, own):
            print(f"🔀 [Translator] 夾雜語言，改用主要文字判斷 {detected_raw} → {source_lang}: {transcript[:40]}")
    for own, other in ((side_a, side_b), (side_b, side_a)):
        if source_lang:
            break
        match = next((c for c in own if _language_matches(detected_lang, c)), None)
        if not match and detected_lang in _MALAY_INDONESIAN:
            # Whisper 常把馬來文認成印尼文（反之亦然），只選了其中一種時視為同一種
            match = next((c for c in own if _language_family(c) in _MALAY_INDONESIAN
                          and not any(_language_matches(detected_lang, x) for x in side_a + side_b)), None)
        if match:
            source_lang, target_lang = match, other[0]
            break
    if not source_lang:
        # 展場旁邊的人講別的語言，或雜音被認成別的語言：安靜略過
        print(f"🔇 [Translator] 略過非選定語言 {detected_raw}: {transcript[:40]}")
        return _empty("other_lang")

    transcript, translated = await _translate_part(transcript, source_lang, target_lang, is_final)
    return TranslatorResponse(
        transcript=transcript,
        translated_text=translated,
        detected_lang=detected_lang,
        source_lang=source_lang,
        target_lang=target_lang,
        confidence=float(stt_result.get("confidence") or 0.0),
    )


def _pick_source(own: list, text: str, detected_lang: str) -> str:
    """這一邊選了好幾種語言時，決定這段話是哪一種"""
    return next((c for c in own if _language_matches(detected_lang, c)), None) or max(
        own, key=lambda c: len(_SCRIPT_PATTERNS[_script_of(c)].findall(text)))


async def _translate_part(text: str, source_lang: str, target_lang: str, is_final: bool):
    if _language_family(source_lang) == "zh":
        converter = _TO_TRADITIONAL if source_lang == "zh-TW" else _TO_SIMPLIFIED
        text = _ZH_PUNCT.sub(lambda m: _ZH_PUNCT_MAP[m.group(1)], converter.convert(text))

    translation = await translation_service.translate_text(
        text,
        target_lang,
        source_lang,
        fast=not is_final,
    )
    if translation.get("error"):
        raise HTTPException(status_code=502, detail="Translation service failed")
    return text, translation.get("text") or ""


@router.get("/quota")
async def get_quota(current_user: str = Depends(get_current_user)):
    """Groq 今天剩餘的呼叫次數（語音辨識、翻譯），翻譯機右上角顯示用"""
    _ = current_user
    return await groq_quota.snapshot()
