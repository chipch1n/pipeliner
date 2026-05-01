import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import User, Session
from ..utils import send_lockout_alert

logger = logging.getLogger("app.auth")

FIXED_SALT = os.getenv("FIXED_SALT")

def hash_password(password: str) -> str:
    salted = FIXED_SALT + password
    return hashlib.sha256(salted.encode('utf-8')).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed

async def create_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        return None
    user = User(
        username=username,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def authenticate_user(db: AsyncSession, username: str, password: str) -> User:
    from fastapi import HTTPException

    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if user.lockout_until and user.lockout_until > now:
        raise HTTPException(
            status_code=423,
            detail=f"Account locked. Try again after {user.lockout_until.strftime('%Y-%m-%d %H:%M:%S')} UTC.",
        )

    if user.lockout_until and user.lockout_until <= now:
        logger.info("Lockout expired for user: %s, clearing counters", username)
        user.lockout_until = None
        user.failed_attempts = 0

    valid = verify_password(password, user.password_hash)

    if valid:
        user.failed_attempts = 0
        user.lockout_until = None
        await db.commit()
        return user
    else:
        user.failed_attempts += 1
        if user.failed_attempts >= 3:
            user.lockout_until = now + timedelta(minutes=10)
            await db.commit()
            await send_lockout_alert(username)
            logger.info("Locked user: %s", username)
            raise HTTPException(
                status_code=423,
                detail="Account locked due to 3 failed attempts.",
            )
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

def generate_session_token() -> str:
    return secrets.token_urlsafe(64)

async def create_session(db: AsyncSession, user_id: int) -> str:
    token = generate_session_token()
    session = Session(token=token, user_id=user_id)
    db.add(session)
    await db.commit()
    return token

async def delete_session(db: AsyncSession, token: str) -> bool:
    stmt = delete(Session).where(Session.token == token)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

async def validate_session_token(db: AsyncSession, token: str) -> Optional[int]:
    stmt = select(Session.user_id).where(Session.token == token)
    result = await db.execute(stmt)
    user_id = result.scalar_one_or_none()
    return user_id