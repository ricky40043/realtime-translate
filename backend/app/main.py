from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import os
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
    allow_origins=origins,      # 不可用 "*"
    allow_credentials=True,     # 若用 Cookie 或需要帶授權
    allow_methods=["*"],
    allow_headers=["*"],
)

# 使用全域連線管理器

# 註冊路由
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
    """WebSocket 連線端點"""
    await manager.connect(websocket, roomId, userId, token)
    try:
        while True:
            data = await websocket.receive_text()
            # 處理客戶端訊息（如果需要）
            await manager.handle_client_message(websocket, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, roomId, userId)

@app.get("/")
async def root():
    return {"message": "Realtime Translation API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}