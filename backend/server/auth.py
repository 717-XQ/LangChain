# -*- coding: utf-8 -*-
"""
auth.py - JWT认证模块（技术栈2.1：python-jose + bcrypt）
=============================================
功能：
  - bcrypt 密码哈希（哈希/校验）
  - python-jose JWT 访问/刷新双Token
  - /auth/register /auth/login /auth/refresh /auth/me
  - FastAPI 依赖注入 get_current_user（Bearer Token）
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from loguru import logger
from sqlalchemy.orm import Session
import bcrypt

from config import get_config
from database import get_db
from models import User
from server.schemas import (
    RegisterRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserInfo,
)

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


# ============================================================
# 密码哈希（bcrypt）
# ============================================================

def hash_password(password: str) -> str:
    """bcrypt哈希密码"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验密码"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ============================================================
# JWT Token（python-jose）
# ============================================================

def _get_auth_config():
    cfg = get_config()
    secret = cfg.auth.jwt_secret
    if secret in ("", "change-me-in-production"):
        logger.warning("JWT_SECRET 使用默认值，生产环境必须通过环境变量设置")
    return cfg.auth


def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    """创建JWT Token"""
    auth = _get_auth_config()
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "type": token_type,          # access / refresh
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, auth.jwt_secret, algorithm=auth.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    """创建访问Token（30分钟）"""
    auth = _get_auth_config()
    return create_token(
        str(user_id), "access",
        timedelta(minutes=auth.access_token_expire_minutes),
    )


def create_refresh_token(user_id: int) -> str:
    """创建刷新Token（7天）"""
    auth = _get_auth_config()
    return create_token(
        str(user_id), "refresh",
        timedelta(days=auth.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str = "access") -> Optional[dict]:
    """解码并校验Token"""
    auth = _get_auth_config()
    try:
        payload = jwt.decode(
            token, auth.jwt_secret,
            algorithms=[auth.jwt_algorithm],
        )
        if payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


# ============================================================
# 依赖注入：当前用户
# ============================================================

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI依赖：从Bearer Token解析当前用户"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证Token",
        )
    payload = decode_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token无效或已过期",
        )
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user


def verify_ws_token(token: str) -> Optional[User]:
    """WebSocket鉴权：校验query中的Token，返回用户（无会话）"""
    payload = decode_token(token, expected_type="access")
    if payload is None:
        return None
    from database import get_session_factory
    factory = get_session_factory()
    db = factory()
    try:
        return db.query(User).filter(User.id == int(payload["sub"])).first()
    except Exception:
        return None
    finally:
        db.close()


# ============================================================
# 认证路由
# ============================================================

def _user_info(user: User) -> UserInfo:
    return UserInfo(id=user.id, username=user.username, email=user.email)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册（自动登录，返回双Token）"""
    username = request.username.strip()
    email = request.email.strip().lower()

    if not re.match(r"^[\w\u4e00-\u9fff-]{3,64}$", username):
        raise HTTPException(status_code=400, detail="用户名格式不合法（3-64字符，字母数字下划线中文）")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="邮箱格式不合法")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(request.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"新用户注册: {username} (id={user.id})")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_info(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """用户登录（返回双Token）"""
    user = db.query(User).filter(User.username == request.username.strip()).first()
    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    logger.info(f"用户登录: {user.username}")
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_info(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    """刷新Token（用刷新Token换新访问Token）"""
    payload = decode_token(request.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新Token无效或已过期",
        )
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_info(user),
    )


@router.get("/me", response_model=UserInfo)
def me(current_user: User = Depends(get_current_user)):
    """当前用户信息"""
    return _user_info(current_user)
