from typing import Set, Dict, List, Optional
import asyncpg
from ..db.repo import RoomRepo, UserRepo

def board_lang_for(speaker: Optional[dict], override: Optional[str], room: Optional[dict]) -> str:
    """講者說話時主板顯示的語言：房間覆寫 > 講者 output_lang > 房間預設"""
    if override:
        return override
    if speaker and speaker.get("output_lang"):
        return speaker["output_lang"]
    return (room or {}).get("default_board_lang") or "zh-TW"

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
        
        # 一次批次查詢所有在線使用者（含講者），取代 N 次個別查詢
        all_ids = list(set(online_users) | {speaker_id})
        users_map = await self.user_repo.get_users_batch(all_ids)

        # 個人視圖：收集所有在線使用者的慣用語（input_lang）
        personal_langs = set()
        for user_id in online_users:
            user = users_map.get(user_id)
            if user:
                user_input_lang = user.get("input_lang") or user.get("preferred_lang", "zh-TW")
                personal_langs.add(user_input_lang)

        # 講者自己的手機顯示自己話語的 output_lang 翻譯（例：講中文、設定輸出英文）
        speaker = users_map.get(speaker_id)
        if speaker and speaker.get("output_lang"):
            personal_langs.add(speaker["output_lang"])

        # 主板視圖：講者在設定裡選的「主板顯示語言」(output_lang)，沒設才用房間預設
        board_lang = board_lang_for(speaker, override_map.get(speaker_id), room)
        
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
