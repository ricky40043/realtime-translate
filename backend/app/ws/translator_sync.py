"""雙向翻譯機的「同步房間」。

手機當麥克風、電腦（或其他手機）開同一個房間，就能即時看到一模一樣的對話畫面。
這裡只負責轉發與保存「目前畫面」的快照（記憶體內），不碰語音辨識／翻譯本身。

連線：  /ws/translator-sync/{room}?token=<JWT>&cid=<這個分頁的隨機代號>

用戶端 → 伺服器
  {"type": "entries", "upserts": [Entry...], "removed": ["key", ...]}
  {"type": "langs", "langA": [...], "langB": [...]}
  {"type": "reset"}            清空房間畫面（「新對話」）
  {"type": "ping"}
伺服器 → 用戶端
  {"type": "snapshot", "entries": [...], "langs": {...}|null, "peers": n, "now": 伺服器毫秒時間}   剛連上時
  {"type": "entries" | "langs" | "reset", ..., "from": cid}                 別台裝置的更新（不會回傳給自己）
  {"type": "peers", "peers": n}                                             房間裝置數變動
  {"type": "pong"}
"""
import asyncio
import json
import os
import re
import time
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

router = APIRouter()

ROOM_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
KEY_MAX_LEN = 80
MAX_ENTRIES = 100            # 一個房間最多保留幾句（和前端畫面一致）
MAX_MESSAGE_BYTES = 256 * 1024
MAX_PEERS_PER_ROOM = 20
EMPTY_ROOM_TTL_SEC = 30 * 60  # 沒人之後保留多久（重新整理、手機斷線重連不會丟畫面）


def _clean_entry(raw: dict) -> Optional[dict]:
    """只留下畫面需要的欄位並限制大小，避免任意資料被存進房間"""
    if not isinstance(raw, dict):
        return None
    key = raw.get("key")
    if not isinstance(key, str) or not key or len(key) > KEY_MAX_LEN:
        return None
    pieces = []
    for p in (raw.get("pieces") or [])[:50]:
        if not isinstance(p, dict):
            continue
        pieces.append({
            "transcript": str(p.get("transcript") or "")[:4000],
            "translation": str(p.get("translation") or "")[:4000],
            "final": bool(p.get("final")),
        })
    t = raw.get("t")
    return {
        "key": key,
        "t": float(t) if isinstance(t, (int, float)) else time.time() * 1000,
        "sourceLang": str(raw.get("sourceLang") or "")[:16],
        "targetLang": str(raw.get("targetLang") or "")[:16],
        "ended": bool(raw.get("ended")),
        "pieces": pieces,
    }


def _clean_langs(raw: dict) -> Optional[dict]:
    out = {}
    for name in ("langA", "langB"):
        value = raw.get(name)
        if not isinstance(value, list) or not value or len(value) > 20:
            return None
        if not all(isinstance(c, str) and 0 < len(c) <= 16 for c in value):
            return None
        out[name] = value
    return out


class _Room:
    def __init__(self) -> None:
        self.sockets: Dict[WebSocket, str] = {}   # websocket -> cid
        self.entries: Dict[str, dict] = {}        # key -> entry
        self.langs: Optional[dict] = None
        self.cleanup: Optional[asyncio.TimerHandle] = None

    def snapshot_entries(self) -> list:
        return sorted(self.entries.values(), key=lambda e: e["t"])

    def trim(self) -> None:
        if len(self.entries) > MAX_ENTRIES:
            for e in self.snapshot_entries()[: len(self.entries) - MAX_ENTRIES]:
                self.entries.pop(e["key"], None)


class TranslatorSyncHub:
    def __init__(self) -> None:
        self.rooms: Dict[str, _Room] = {}

    async def join(self, room_id: str, ws: WebSocket, cid: str) -> bool:
        room = self.rooms.setdefault(room_id, _Room())
        if len(room.sockets) >= MAX_PEERS_PER_ROOM:
            return False
        if room.cleanup:
            room.cleanup.cancel()
            room.cleanup = None
        room.sockets[ws] = cid
        await self._send(ws, {
            "type": "snapshot",
            "entries": room.snapshot_entries(),
            "langs": room.langs,
            "peers": len(room.sockets),
            "now": time.time() * 1000,   # 各裝置時鐘會差幾秒；前端用這個校正，對話順序才不會亂
        })
        await self._broadcast(room, {"type": "peers", "peers": len(room.sockets)}, exclude=ws)
        return True

    async def leave(self, room_id: str, ws: WebSocket) -> None:
        room = self.rooms.get(room_id)
        if not room or ws not in room.sockets:
            return
        room.sockets.pop(ws, None)
        if room.sockets:
            await self._broadcast(room, {"type": "peers", "peers": len(room.sockets)})
            return
        # 沒人了：先保留一陣子，免得重新整理或手機網路閃斷就把畫面弄丟
        loop = asyncio.get_running_loop()
        room.cleanup = loop.call_later(EMPTY_ROOM_TTL_SEC, self._drop_if_empty, room_id)

    def _drop_if_empty(self, room_id: str) -> None:
        room = self.rooms.get(room_id)
        if room and not room.sockets:
            del self.rooms[room_id]

    async def handle(self, room_id: str, ws: WebSocket, message: dict) -> None:
        room = self.rooms.get(room_id)
        if not room:
            return
        cid = room.sockets.get(ws, "")
        kind = message.get("type")
        if kind == "ping":
            await self._send(ws, {"type": "pong"})
        elif kind == "entries":
            upserts = [e for e in (_clean_entry(x) for x in (message.get("upserts") or [])[:200]) if e]
            removed = [k for k in (message.get("removed") or [])[:200] if isinstance(k, str)]
            for e in upserts:
                room.entries[e["key"]] = e
            for k in removed:
                room.entries.pop(k, None)
            room.trim()
            if upserts or removed:
                await self._broadcast(room, {"type": "entries", "upserts": upserts, "removed": removed, "from": cid}, exclude=ws)
        elif kind == "langs":
            langs = _clean_langs(message)
            if langs and langs != room.langs:
                room.langs = langs
                await self._broadcast(room, {"type": "langs", **langs, "from": cid}, exclude=ws)
        elif kind == "reset":
            room.entries.clear()
            await self._broadcast(room, {"type": "reset", "from": cid}, exclude=ws)

    async def _send(self, ws: WebSocket, message: dict) -> None:
        await ws.send_text(json.dumps(message, ensure_ascii=False))

    async def _broadcast(self, room: _Room, message: dict, exclude: Optional[WebSocket] = None) -> None:
        for peer in list(room.sockets):
            if peer is exclude:
                continue
            try:
                await self._send(peer, message)
            except Exception:
                # 送不出去的連線交給它自己的接收迴圈在斷線時清理
                pass


hub = TranslatorSyncHub()


def _token_valid(token: str) -> bool:
    try:
        jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        return True
    except JWTError:
        return False


@router.websocket("/ws/translator-sync/{room_id}")
async def translator_sync_ws(websocket: WebSocket, room_id: str, token: str = "", cid: str = ""):
    if not ROOM_RE.match(room_id):
        await websocket.close(code=4400, reason="Invalid room")
        return
    if not _token_valid(token):
        await websocket.close(code=4001, reason="Invalid token")
        return
    await websocket.accept()
    cid = cid[:40]
    if not await hub.join(room_id, websocket, cid):
        await websocket.close(code=4429, reason="Room is full")
        return
    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > MAX_MESSAGE_BYTES:
                continue
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                await hub.handle(room_id, websocket, message)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(room_id, websocket)
