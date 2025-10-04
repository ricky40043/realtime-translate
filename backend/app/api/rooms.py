from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import asyncpg
from ..deps import get_db, get_current_user
from ..db.repo import RoomRepo, UserRepo

router = APIRouter()

class CreateRoomRequest(BaseModel):
    name: str
    default_board_lang: str = "en"

class RoomResponse(BaseModel):
    id: str
    name: str
    default_board_lang: str
    created_at: str

class UpdateBoardLangRequest(BaseModel):
    default_board_lang: str

class LangOverride(BaseModel):
    speakerId: str
    targetLang: str

class UpdateOverridesRequest(BaseModel):
    overrides: List[LangOverride]

class UpdateUserLangRequest(BaseModel):
    preferred_lang: str

@router.post("", response_model=RoomResponse)
async def create_room(
    request: CreateRoomRequest, 
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """建立房間"""
    try:
        room_repo = RoomRepo(db)
        room_id = await room_repo.create_room(
            name=request.name,
            default_board_lang=request.default_board_lang
        )
        
        room = await room_repo.get_room(room_id)
        return RoomResponse(
            id=str(room["id"]),
            name=room["name"],
            default_board_lang=room["default_board_lang"],
            created_at=room["created_at"].isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create room: {str(e)}")

@router.get("/{room_id}")
async def get_room(
    room_id: str,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """取得房間資訊"""
    try:
        room_repo = RoomRepo(db)
        room = await room_repo.get_room(room_id)
        
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        overrides = await room_repo.get_lang_overrides(room_id)
        
        return {
            "id": str(room["id"]),
            "name": room["name"],
            "default_board_lang": room["default_board_lang"],
            "created_at": room["created_at"].isoformat(),
            "overrides": overrides
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get room: {str(e)}")

@router.put("/{room_id}/board-lang")
async def update_board_lang(
    room_id: str,
    request: UpdateBoardLangRequest,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """更新主板語言"""
    try:
        room_repo = RoomRepo(db)
        
        # 檢查房間是否存在
        room = await room_repo.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        await room_repo.update_board_lang(room_id, request.default_board_lang)
        return {"message": "Board language updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update board language: {str(e)}")

@router.put("/{room_id}/overrides")
async def update_overrides(
    room_id: str,
    request: UpdateOverridesRequest,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """批次更新語言覆寫"""
    try:
        room_repo = RoomRepo(db)
        
        # 檢查房間是否存在
        room = await room_repo.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # 轉換格式
        overrides_data = [
            {"speakerId": override.speakerId, "targetLang": override.targetLang}
            for override in request.overrides
        ]
        
        await room_repo.set_lang_overrides(room_id, overrides_data)
        return {"message": "Language overrides updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update overrides: {str(e)}")

@router.put("/users/{user_id}/preferred-lang")
async def update_user_preferred_lang(
    user_id: str,
    request: UpdateUserLangRequest,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """更新使用者偏好語言"""
    try:
        # 只能更新自己的語言設定
        if current_user != user_id:
            raise HTTPException(status_code=403, detail="Permission denied")
        
        user_repo = UserRepo(db)
        
        # 檢查使用者是否存在
        user = await user_repo.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        await user_repo.update_preferred_lang(user_id, request.preferred_lang)
        return {"message": "Preferred language updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preferred language: {str(e)}")