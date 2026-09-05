import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from .config import settings
from .models import ReaderSession, User, utcnow
from .security import ALGORITHM, DbSession

ACCESS_TOKEN_TYPE = "reader_access"
LICENSE_TOKEN_TYPE = "book_license"
REFRESH_BYTES = 32
bearer = HTTPBearer(auto_error=False)


def _refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_reader_tokens(db: DbSession, user: User) -> dict:
    now = datetime.now(UTC)
    access = jwt.encode(
        {
            "sub": str(user.id),
            "typ": ACCESS_TOKEN_TYPE,
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    refresh = secrets.token_urlsafe(REFRESH_BYTES)
    session = ReaderSession(
        user_id=user.id,
        refresh_token_hash=_refresh_hash(refresh),
        expires_at=now + timedelta(days=settings.refresh_token_days),
    )
    db.add(session)
    db.commit()
    return {
        "accessToken": access,
        "refreshToken": refresh,
        "expiresIn": settings.access_token_minutes * 60,
        "user": reader_user_json(user),
    }


def rotate_reader_tokens(db: DbSession, refresh_token: str) -> dict:
    session = db.scalar(
        select(ReaderSession).where(
            ReaderSession.refresh_token_hash == _refresh_hash(refresh_token)
        )
    )
    now = utcnow()
    if not session or session.revoked_at or session.expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reader session expired")
    user = db.get(User, session.user_id)
    if not user or user.role != "user" or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reader session expired")
    session.revoked_at = now
    db.commit()
    return issue_reader_tokens(db, user)


def revoke_refresh_token(db: DbSession, refresh_token: str) -> None:
    session = db.scalar(
        select(ReaderSession).where(
            ReaderSession.refresh_token_hash == _refresh_hash(refresh_token)
        )
    )
    if session and not session.revoked_at:
        session.revoked_at = utcnow()
        db.commit()


def require_reader(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reader login required")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("typ") != ACCESS_TOKEN_TYPE:
            raise ValueError("Wrong token type")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reader login required") from error
    user = db.get(User, user_id)
    if not user or user.role != "user" or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reader login required")
    user.last_active_at = utcnow()
    db.commit()
    return user


ReaderUser = Annotated[User, Depends(require_reader)]


def reader_user_json(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "preferredLocale": user.preferred_locale,
    }


def _license_private_key() -> ed25519.Ed25519PrivateKey:
    seed = hashlib.sha256(f"bookino-license:{settings.jwt_secret}".encode()).digest()
    return ed25519.Ed25519PrivateKey.from_private_bytes(seed)


def license_public_key() -> str:
    raw = (
        _license_private_key()
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    return base64.b64encode(raw).decode()


def protect_dek_for_device(dek: bytes, public_key_pem: str) -> str:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
            raise ValueError("RSA key must be at least 2048 bits")
        encrypted = key.encrypt(
            dek,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return base64.b64encode(encrypted).decode()
    except (ValueError, TypeError) as error:
        raise HTTPException(422, "Invalid device public key") from error


def issue_license_token(
    *,
    user_id: uuid.UUID,
    device_id: uuid.UUID,
    book_id: uuid.UUID,
    version_id: uuid.UUID,
    protected_key: str,
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    valid_until = now + timedelta(days=settings.offline_license_days)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "typ": LICENSE_TOKEN_TYPE,
            "device_id": str(device_id),
            "book_id": str(book_id),
            "book_version_id": str(version_id),
            "protected_key": protected_key,
            "iat": now,
            "exp": valid_until,
        },
        _license_private_key(),
        algorithm="EdDSA",
    )
    return token, valid_until
