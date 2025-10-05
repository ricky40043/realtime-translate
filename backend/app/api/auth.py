from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from jose import jwt
import os
from datetime import datetime, timedelta
import asyncpg
from ..deps import get_db, get_current_user
from ..db.repo import UserRepo

router = APIRouter()

class GuestLoginRequest(BaseModel):
    display_name: str
    preferred_lang: str = "zh-TW"
    input_lang: str = ""
    output_lang: str = "zh-TW"

class AuthResponse(BaseModel):
    user_id: str
    token: str
    display_name: str
    preferred_lang: str
    input_lang: str
    output_lang: str

@router.post("/guest", response_model=AuthResponse)
async def guest_login(request: GuestLoginRequest, db: asyncpg.Connection = Depends(get_db)):
    """匿名登入，建立訪客使用者"""
    try:
        user_repo = UserRepo(db)
        user_id = await user_repo.create_guest_user(
            display_name=request.display_name,
            preferred_lang=request.preferred_lang,
            input_lang=request.input_lang,
            output_lang=request.output_lang
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
            preferred_lang=request.preferred_lang,
            input_lang=request.input_lang,
            output_lang=request.output_lang
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create guest user: {str(e)}")

class UpdateLanguageRequest(BaseModel):
    preferred_lang: str

class UpdateLanguagesRequest(BaseModel):
    input_lang: str
    output_lang: str

@router.put("/update-lang")
async def update_user_language(
    request: UpdateLanguageRequest,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """更新用戶語言偏好（舊版本相容）"""
    try:
        user_repo = UserRepo(db)
        await user_repo.update_preferred_lang(current_user, request.preferred_lang)
        
        return {"message": "Language preference updated", "preferred_lang": request.preferred_lang}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update language: {str(e)}")

@router.put("/update-langs")
async def update_user_languages(
    request: UpdateLanguagesRequest,
    current_user: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """更新用戶輸入和輸出語言"""
    try:
        user_repo = UserRepo(db)
        await user_repo.update_user_languages(current_user, request.input_lang, request.output_lang)
        
        return {
            "message": "Languages updated", 
            "input_lang": request.input_lang,
            "output_lang": request.output_lang
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update languages: {str(e)}")

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