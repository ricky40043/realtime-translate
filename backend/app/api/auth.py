from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from jose import jwt
import os
from datetime import datetime, timedelta
import asyncpg
from ..deps import get_db
from ..db.repo import UserRepo

router = APIRouter()

class GuestLoginRequest(BaseModel):
    display_name: str
    preferred_lang: str = "zh-TW"

class AuthResponse(BaseModel):
    user_id: str
    token: str
    display_name: str
    preferred_lang: str

@router.post("/guest", response_model=AuthResponse)
async def guest_login(request: GuestLoginRequest, db: asyncpg.Connection = Depends(get_db)):
    """匿名登入，建立訪客使用者"""
    try:
        user_repo = UserRepo(db)
        user_id = await user_repo.create_guest_user(
            display_name=request.display_name,
            preferred_lang=request.preferred_lang
        )
        
        # 產生 JWT token
        access_token_expires = timedelta(days=7)  # 7天有效
        access_token = create_access_token(
            data={"sub": user_id}, expires_delta=access_token_expires
        )
        
        return AuthResponse(
            user_id=user_id,
            token=access_token,
            display_name=request.display_name,
            preferred_lang=request.preferred_lang
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create guest user: {str(e)}")

def create_access_token(data: dict, expires_delta: timedelta = None):
    """建立 JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv("JWT_SECRET"), algorithm="HS256")
    return encoded_jwt