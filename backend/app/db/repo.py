import asyncpg
from typing import List, Dict, Optional, Any
from uuid import UUID
import uuid

class UserRepo:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
    
    async def create_guest_user(self, display_name: str, preferred_lang: str, input_lang: str = "zh-TW", output_lang: str = "en") -> str:
        """建立匿名使用者"""
        user_id = str(uuid.uuid4())
        
        # 檢查並添加欄位（如果不存在）
        try:
            await self.conn.execute("ALTER TABLE app_user ADD COLUMN IF NOT EXISTS input_lang VARCHAR(10) DEFAULT 'zh-TW'")
            await self.conn.execute("ALTER TABLE app_user ADD COLUMN IF NOT EXISTS output_lang VARCHAR(10) DEFAULT 'en'")
        except:
            pass  # 欄位可能已存在
        
        await self.conn.execute(
            "INSERT INTO app_user (id, display_name, preferred_lang, input_lang, output_lang) VALUES ($1, $2, $3, $4, $5)",
            user_id, display_name, preferred_lang, input_lang, output_lang
        )
        return user_id
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """取得使用者資料"""
        try:
            row = await self.conn.fetchrow(
                "SELECT id, display_name, preferred_lang, input_lang, output_lang, created_at FROM app_user WHERE id = $1",
                user_id
            )
        except:
            # 如果新欄位不存在，使用舊格式
            row = await self.conn.fetchrow(
                "SELECT id, display_name, preferred_lang, created_at FROM app_user WHERE id = $1",
                user_id
            )
        return dict(row) if row else None
    
    async def update_preferred_lang(self, user_id: str, preferred_lang: str):
        """更新使用者偏好語言"""
        await self.conn.execute(
            "UPDATE app_user SET preferred_lang = $2 WHERE id = $1",
            user_id, preferred_lang
        )
    
    async def update_user_languages(self, user_id: str, input_lang: str, output_lang: str):
        """更新使用者輸入和輸出語言"""
        await self.conn.execute(
            "UPDATE app_user SET input_lang = $2, output_lang = $3 WHERE id = $1",
            user_id, input_lang, output_lang
        )

class RoomRepo:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
    
    async def create_room(self, name: str, default_board_lang: str) -> str:
        """建立房間"""
        room_id = str(uuid.uuid4())
        await self.conn.execute(
            "INSERT INTO room (id, name, default_board_lang) VALUES ($1, $2, $3)",
            room_id, name, default_board_lang
        )
        return room_id
    
    async def get_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        """取得房間資料"""
        row = await self.conn.fetchrow(
            "SELECT id, name, default_board_lang, created_at FROM room WHERE id = $1",
            room_id
        )
        return dict(row) if row else None
    
    async def update_board_lang(self, room_id: str, default_board_lang: str):
        """更新主板語言"""
        await self.conn.execute(
            "UPDATE room SET default_board_lang = $2 WHERE id = $1",
            room_id, default_board_lang
        )
    
    async def set_lang_overrides(self, room_id: str, overrides: List[Dict[str, str]]):
        """設定語言覆寫"""
        # 先刪除現有覆寫
        await self.conn.execute(
            "DELETE FROM room_lang_override WHERE room_id = $1",
            room_id
        )
        
        # 插入新的覆寫
        for override in overrides:
            await self.conn.execute(
                "INSERT INTO room_lang_override (room_id, speaker_id, target_lang) VALUES ($1, $2, $3)",
                room_id, override["speakerId"], override["targetLang"]
            )
    
    async def get_lang_overrides(self, room_id: str) -> List[Dict[str, str]]:
        """取得語言覆寫"""
        rows = await self.conn.fetch(
            "SELECT speaker_id, target_lang FROM room_lang_override WHERE room_id = $1",
            room_id
        )
        return [{"speakerId": row["speaker_id"], "targetLang": row["target_lang"]} for row in rows]

class MessageRepo:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
    
    async def create_message(self, room_id: str, speaker_id: str, text: str, 
                           source_lang: Optional[str] = None, is_final: bool = True) -> str:
        """建立訊息"""
        message_id = str(uuid.uuid4())
        await self.conn.execute(
            """INSERT INTO message (id, room_id, speaker_id, source_lang, text, is_final) 
               VALUES ($1, $2, $3, $4, $5, $6)""",
            message_id, room_id, speaker_id, source_lang, text, is_final
        )
        return message_id
    
    async def save_translation(self, message_id: str, target_lang: str, text: str, 
                             latency_ms: Optional[int] = None, quality: Optional[float] = None):
        """儲存翻譯"""
        await self.conn.execute(
            """INSERT INTO message_translation (message_id, target_lang, text, latency_ms, quality)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (message_id, target_lang) 
               DO UPDATE SET text = $3, latency_ms = $4, quality = $5""",
            message_id, target_lang, text, latency_ms, quality
        )
    
    async def get_room_messages(self, room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """取得房間訊息"""
        rows = await self.conn.fetch(
            """SELECT m.id, m.room_id, m.speaker_id, m.source_lang, m.text, 
                      m.is_final, m.created_at, u.display_name
               FROM message m
               LEFT JOIN app_user u ON m.speaker_id = u.id
               WHERE m.room_id = $1 AND m.is_final = true
               ORDER BY m.created_at DESC
               LIMIT $2""",
            room_id, limit
        )
        return [dict(row) for row in rows]
    
    async def get_message_translations(self, message_id: str) -> List[Dict[str, Any]]:
        """取得訊息翻譯"""
        rows = await self.conn.fetch(
            "SELECT target_lang, text, latency_ms, quality FROM message_translation WHERE message_id = $1",
            message_id
        )
        return [dict(row) for row in rows]