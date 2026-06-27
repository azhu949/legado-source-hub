"""管理后台认证路由。"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.core.auth import create_access_token, get_current_user, verify_password
from app.models.responses import success, error
from app.models.source import LoginRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/auth", tags=["auth"])


@router.post("/login")
async def login(req: LoginRequest):
    """管理员登录，返回 JWT Token。"""
    settings = get_settings()
    if req.username != settings.ADMIN_USER or not verify_password(
        req.password, settings.ADMIN_PASS
    ):
        return error("UNAUTHORIZED", "用户名或密码错误")

    token = create_access_token(req.username)
    return success(
        data={
            "access_token": token,
            "token_type": "bearer",
            "username": req.username,
            "expires_in": settings.JWT_EXPIRE_HOURS * 3600,
        }
    )


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return success(data={"username": user["username"]})
