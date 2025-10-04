from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import json
from datetime import datetime
from jose import jwt, JWTError
import os

class ConnectionManager:
    def __init__(self):
        # 房間 -> 使用者 -> WebSocket 連線
        self.rooms: Dict[str, Dict[str, WebSocket]] = {}
        # WebSocket -> (room_id, user_id) 的反向對映
        self.connections: Dict[WebSocket, tuple] = {}
    
    async def connect(self, websocket: WebSocket, room_id: str, user_id: str, token: str):
        """建立 WebSocket 連線"""
        # 驗證 JWT token
        if not await self._verify_token(token, user_id):
            await websocket.close(code=4001, reason="Invalid token")
            return
        
        await websocket.accept()
        
        # 初始化房間
        if room_id not in self.rooms:
            self.rooms[room_id] = {}
        
        # 斷開該使用者的舊連線（如果存在）
        if user_id in self.rooms[room_id]:
            old_websocket = self.rooms[room_id][user_id]
            if old_websocket in self.connections:
                del self.connections[old_websocket]
            try:
                await old_websocket.close()
            except:
                pass
        
        # 建立新連線
        self.rooms[room_id][user_id] = websocket
        self.connections[websocket] = (room_id, user_id)
        
        # 發送連線成功訊息
        await self.send_to_websocket(websocket, {
            "type": "connection.established",
            "roomId": room_id,
            "userId": user_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        print(f"User {user_id} connected to room {room_id}")
    
    def disconnect(self, websocket: WebSocket, room_id: str, user_id: str):
        """斷開 WebSocket 連線"""
        # 清除連線記錄
        if websocket in self.connections:
            del self.connections[websocket]
        
        if room_id in self.rooms and user_id in self.rooms[room_id]:
            del self.rooms[room_id][user_id]
            
            # 如果房間沒有人了，清除房間
            if not self.rooms[room_id]:
                del self.rooms[room_id]
        
        print(f"User {user_id} disconnected from room {room_id}")
    
    async def send_to_user(self, room_id: str, user_id: str, message: dict):
        """發送訊息給特定使用者"""
        if room_id in self.rooms and user_id in self.rooms[room_id]:
            websocket = self.rooms[room_id][user_id]
            await self.send_to_websocket(websocket, message)
    
    async def broadcast_to_room(self, room_id: str, message: dict):
        """廣播訊息給房間內所有使用者"""
        if room_id in self.rooms:
            disconnected = []
            for user_id, websocket in self.rooms[room_id].items():
                try:
                    await self.send_to_websocket(websocket, message)
                except:
                    # 記錄需要清理的斷線連線
                    disconnected.append((websocket, room_id, user_id))
            
            # 清理斷線的連線
            for websocket, room_id, user_id in disconnected:
                self.disconnect(websocket, room_id, user_id)
    
    async def send_to_websocket(self, websocket: WebSocket, message: dict):
        """發送訊息給 WebSocket 連線"""
        try:
            # 加上時間戳
            if "timestamp" not in message or message["timestamp"] is None:
                message["timestamp"] = datetime.utcnow().isoformat()
            
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
        except Exception as e:
            print(f"Error sending message to websocket: {e}")
            raise
    
    async def handle_client_message(self, websocket: WebSocket, data: str):
        """處理客戶端發送的訊息"""
        try:
            message = json.loads(data)
            message_type = message.get("type")
            
            if message_type == "client.prefLang.update":
                # 處理使用者語言偏好更新
                await self._handle_pref_lang_update(websocket, message)
            elif message_type == "ping":
                # 處理心跳
                await self.send_to_websocket(websocket, {"type": "pong"})
        except json.JSONDecodeError:
            await self.send_to_websocket(websocket, {
                "type": "error",
                "message": "Invalid JSON format"
            })
        except Exception as e:
            await self.send_to_websocket(websocket, {
                "type": "error", 
                "message": str(e)
            })
    
    async def get_room_users(self, room_id: str) -> List[str]:
        """取得房間內的使用者列表"""
        if room_id in self.rooms:
            return list(self.rooms[room_id].keys())
        return []
    
    async def get_room_count(self, room_id: str) -> int:
        """取得房間內的使用者數量"""
        if room_id in self.rooms:
            return len(self.rooms[room_id])
        return 0
    
    async def _verify_token(self, token: str, expected_user_id: str) -> bool:
        """驗證 JWT token"""
        try:
            payload = jwt.decode(
                token, 
                os.getenv("JWT_SECRET"), 
                algorithms=["HS256"]
            )
            user_id = payload.get("sub")
            return user_id == expected_user_id
        except JWTError:
            return False
    
    async def _handle_pref_lang_update(self, websocket: WebSocket, message: dict):
        """處理使用者語言偏好更新"""
        # 這裡可以觸發重新翻譯最近的訊息，或通知其他服務
        # 目前只回覆確認
        await self.send_to_websocket(websocket, {
            "type": "client.prefLang.updated",
            "preferred_lang": message.get("preferred_lang")
        })

# 全域連線管理器實例
manager = ConnectionManager()