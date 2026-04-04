from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import os
from pathlib import Path
from dotenv import load_dotenv

from .api import auth, rooms, ingest, speech, speech_staged
from .ws.hub import manager
from .db.pool import init_db

load_dotenv()

app = FastAPI(title="Realtime Translation API", version="1.0.0")

origins = [
    "http://localhost",
    "http://localhost:80", 
    "http://localhost:5173",
    "http://localhost:8081",
    "https://ecf5f74f766d.ngrok-free.app",
    "*",  # 臨時允許所有來源進行測試
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(speech.router, prefix="/api/speech", tags=["speech"])
app.include_router(speech_staged.router, prefix="/api/speech-staged", tags=["speech-staged"])

@app.on_event("startup")
async def startup_event():
    await init_db()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, roomId: str, userId: str, token: str):
    await manager.connect(websocket, roomId, userId, token)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle_client_message(websocket, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, roomId, userId)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ── SPA Frontend ──────────────────────────────────────────────────
STATIC_DIR = Path("/app/static")

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")

# 全域 404 處置器：如果找不到路由（例如 /user），而且不是 API 請求，就回傳 index.html 讓 Vue 處理
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if STATIC_DIR.exists():
            index_file = STATIC_DIR / "index.html"
            if index_file.exists():
                return FileResponse(str(index_file))
    return JSONResponse({"detail": str(exc.detail)}, status_code=exc.status_code)
