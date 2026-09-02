import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Response, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, utcnow

COOKIE_NAME = "book_admin_session"
ALGORITHM = "HS256"
TOKEN_MINUTES = 30
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    return bool(encoded and password_hash.verify(password, encoded))


def set_session_cookie(response: Response, user: User) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=TOKEN_MINUTES)},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_MINUTES * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax", secure=settings.cookie_secure)


def optional_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return None
    user.last_active_at = utcnow()
    db.commit()
    return user


def require_admin(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if not user or user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_db)]
