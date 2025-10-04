from typing import Set, Dict, List, Optional
import asyncpg
from ..db.repo import RoomRepo, UserRepo

class LanguageRouter:
    """語言路由邏輯，決定訊息需要翻譯成哪些語言"""
    
    def __init__(self, db: asyncpg.Connection):
        self.db = db
        self.room_repo = RoomRepo(db)
        self.user_repo = UserRepo(db)
    
    async def get_target_languages(self, room_id: str, speaker_id: str, 
                                 online_users: List[str]) -> Dict[str, Set[str]]:
        """
        取得目標語言集合
        回傳格式：{
            "personal": {"zh-TW", "en", "ja"},  # 個人視圖需要的語言
            "board": {"en"}  # 主板視圖需要的語言
        }
        """
        # 取得房間資訊
        room = await self.room_repo.get_room(room_id)
        if not room:
            return {"personal": set(), "board": set()}
        
        # 取得語言覆寫設定
        overrides = await self.room_repo.get_lang_overrides(room_id)
        override_map = {ov["speakerId"]: ov["targetLang"] for ov in overrides}
        
        # 個人視圖：收集所有在線使用者的偏好語言
        personal_langs = set()
        for user_id in online_users:
            user = await self.user_repo.get_user(user_id)
            if user:
                personal_langs.add(user["preferred_lang"])
        
        # 主板視圖：使用講者的覆寫語言或預設主板語言
        board_lang = override_map.get(speaker_id, room["default_board_lang"])
        board_langs = {board_lang}
        
        return {
            "personal": personal_langs,
            "board": board_langs
        }
    
    async def get_all_target_languages(self, room_id: str, speaker_id: str, 
                                     online_users: List[str]) -> Set[str]:
        """取得所有需要的目標語言（個人視圖 + 主板視圖）"""
        lang_sets = await self.get_target_languages(room_id, speaker_id, online_users)
        return lang_sets["personal"] | lang_sets["board"]