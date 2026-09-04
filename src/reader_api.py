import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse
from jwt import PyJWKClient
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from .config import settings
from .models import (
    Book,
    BookLicense,
    Bookmark,
    Device,
    Favorite,
    ReadingEvent,
    ReadingProgress,
    User,
    utcnow,
)
from .reader_schemas import (
    BookmarkInput,
    DeviceRegistration,
    FavoriteMutation,
    GoogleLogin,
    LocaleInput,
    ProgressInput,
    ReaderLogin,
    ReaderRegistration,
    RefreshRequest,
)
from .reader_security import (
    ReaderUser,
    issue_license_token,
    issue_reader_tokens,
    license_public_key,
    protect_dek_for_device,
    reader_user_json,
    revoke_refresh_token,
    rotate_reader_tokens,
)
from .security import DbSession, hash_password, verify_password
from .storage import protected_book_file, unwrap_dek

router = APIRouter(prefix="/api/v1/reader", tags=["reader"])


def _uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise HTTPException(422, f"Invalid {field}") from error


def _device(db: DbSession, user: User, device_id: uuid.UUID) -> Device:
    device = db.scalar(select(Device).where(Device.id == device_id, Device.user_id == user.id))
    if not device or device.revoked_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Device is not active")
    device.last_seen_at = utcnow()
    return device


def _published_book(db: DbSession, book_id: uuid.UUID) -> Book:
    book = db.scalar(
        select(Book)
        .where(Book.id == book_id, Book.status == "published")
        .options(joinedload(Book.current_version))
    )
    if not book or not book.current_version or book.current_version.status != "ready":
        raise HTTPException(404, "Book not found")
    return book


def _device_json(item: Device, current: uuid.UUID | None = None) -> dict:
    return {
        "id": str(item.id),
        "installationId": item.installation_id,
        "platform": item.platform,
        "displayName": item.display_name,
        "registeredAt": item.registered_at.isoformat(),
        "lastSeenAt": item.last_seen_at.isoformat(),
        "isCurrent": item.id == current,
        "isRevoked": item.revoked_at is not None,
    }


def _progress_json(item: ReadingProgress) -> dict:
    return {
        "bookId": str(item.book_id),
        "bookVersionId": str(item.book_version_id),
        "deviceId": str(item.device_id),
        "pageNumber": item.page_number,
        "normalizedOffset": item.normalized_offset,
        "readerMode": item.reader_mode,
        "percentage": item.percentage,
        "lastReadAtClient": (
            item.last_read_at_client.isoformat() if item.last_read_at_client else None
        ),
        "syncedAtServer": item.synced_at_server.isoformat(),
    }


def _bookmark_json(item: Bookmark) -> dict:
    return {
        "id": str(item.id),
        "bookId": str(item.book_id),
        "bookVersionId": str(item.book_version_id),
        "pageNumber": item.page_number,
        "normalizedOffset": item.normalized_offset,
        "label": item.label,
        "createdAt": item.created_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
    }


@router.get("/config")
def reader_config() -> dict:
    return {
        "offlineLicenseDays": settings.offline_license_days,
        "maxDevices": 3,
        "licensePublicKey": license_public_key(),
        "googleEnabled": bool(settings.google_client_ids),
    }


@router.post("/auth/register", status_code=201)
def register(payload: ReaderRegistration, db: DbSession) -> dict:
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        username=email,
        email=email,
        display_name=payload.displayName.strip() if payload.displayName else None,
        password_hash=hash_password(payload.password),
        role="user",
        preferred_locale="fa",
    )
    db.add(user)
    db.flush()
    return issue_reader_tokens(db, user)


@router.post("/auth/login")
def login(payload: ReaderLogin, db: DbSession) -> dict:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if (
        not user
        or user.role != "user"
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return issue_reader_tokens(db, user)


@router.post("/auth/google")
def google_login(payload: GoogleLogin, db: DbSession) -> dict:
    if not settings.google_client_ids:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google login is not configured")
    try:
        signing_key = PyJWKClient(
            "https://www.googleapis.com/oauth2/v3/certs"
        ).get_signing_key_from_jwt(payload.idToken)
        claims = jwt.decode(
            payload.idToken,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_ids,
            issuer=["accounts.google.com", "https://accounts.google.com"],
        )
        if not claims.get("email_verified") or not claims.get("email"):
            raise ValueError("Google email is not verified")
    except (jwt.PyJWTError, ValueError) as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google identity") from error
    email = str(claims["email"]).strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user:
        user = User(
            username=email,
            email=email,
            display_name=claims.get("name"),
            role="user",
            preferred_locale="fa",
        )
        db.add(user)
        db.flush()
    if user.role != "user" or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Reader account is unavailable")
    return issue_reader_tokens(db, user)


@router.post("/auth/refresh")
def refresh(payload: RefreshRequest, db: DbSession) -> dict:
    return rotate_reader_tokens(db, payload.refreshToken)


@router.post("/auth/logout", status_code=204)
def logout(payload: RefreshRequest, db: DbSession) -> None:
    revoke_refresh_token(db, payload.refreshToken)


@router.get("/me")
def me(user: ReaderUser) -> dict:
    return reader_user_json(user)


@router.put("/me/locale")
def update_locale(payload: LocaleInput, user: ReaderUser, db: DbSession) -> dict:
    user.preferred_locale = payload.locale
    db.commit()
    return reader_user_json(user)


@router.post("/devices")
def register_device(payload: DeviceRegistration, user: ReaderUser, db: DbSession) -> dict:
    db.execute(select(User).where(User.id == user.id).with_for_update())
    device = db.scalar(
        select(Device).where(
            Device.user_id == user.id, Device.installation_id == payload.installationId
        )
    )
    if device and device.revoked_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Device has been revoked")
    if not device:
        active_count = db.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.user_id == user.id, Device.revoked_at.is_(None))
        )
        if active_count >= 3:
            raise HTTPException(status.HTTP_409_CONFLICT, "Device limit reached")
        device = Device(user_id=user.id, installation_id=payload.installationId)
        db.add(device)
    device.platform = payload.platform
    device.display_name = payload.displayName
    device.public_key = payload.publicKey
    device.metadata_json = {"appVersion": payload.appVersion}
    device.last_seen_at = utcnow()
    db.commit()
    db.refresh(device)
    return _device_json(device, device.id)


@router.get("/devices")
def list_devices(
    user: ReaderUser,
    db: DbSession,
    current_device: Annotated[str | None, Header(alias="X-Device-Id")] = None,
) -> list[dict]:
    current_id = _uuid(current_device, "device id") if current_device else None
    devices = db.scalars(
        select(Device).where(Device.user_id == user.id).order_by(Device.last_seen_at.desc())
    ).all()
    return [_device_json(item, current_id) for item in devices]


@router.delete("/devices/{device_id}", status_code=204)
def revoke_device(device_id: uuid.UUID, user: ReaderUser, db: DbSession) -> None:
    device = db.scalar(select(Device).where(Device.id == device_id, Device.user_id == user.id))
    if not device:
        raise HTTPException(404, "Device not found")
    device.revoked_at = utcnow()
    licenses = db.scalars(
        select(BookLicense).where(
            BookLicense.device_id == device.id, BookLicense.revoked_at.is_(None)
        )
    ).all()
    for license_record in licenses:
        license_record.revoked_at = utcnow()
    db.commit()


@router.post("/books/{book_id}/license")
def issue_book_license(
    book_id: uuid.UUID,
    user: ReaderUser,
    db: DbSession,
    device_header: Annotated[str, Header(alias="X-Device-Id")],
) -> dict:
    device = _device(db, user, _uuid(device_header, "device id"))
    book = _published_book(db, book_id)
    if not device.public_key:
        raise HTTPException(422, "Device public key is missing")
    version = book.current_version
    dek = unwrap_dek(version.wrapped_dek, version.id)
    protected_key = protect_dek_for_device(dek, device.public_key)
    token, valid_until = issue_license_token(
        user_id=user.id,
        device_id=device.id,
        book_id=book.id,
        version_id=version.id,
        protected_key=protected_key,
    )
    existing = db.scalar(
        select(BookLicense).where(
            BookLicense.user_id == user.id,
            BookLicense.device_id == device.id,
            BookLicense.book_version_id == version.id,
        )
    )
    if not existing:
        existing = BookLicense(
            user_id=user.id,
            device_id=device.id,
            book_id=book.id,
            book_version_id=version.id,
            valid_until=valid_until,
            protected_key_payload=token,
        )
        db.add(existing)
    else:
        existing.issued_at = utcnow()
        existing.valid_until = valid_until
        existing.revoked_at = None
        existing.protected_key_payload = token
    db.commit()
    return {
        "license": token,
        "validUntil": valid_until.isoformat(),
        "bookId": str(book.id),
        "bookVersionId": str(version.id),
        "encryptedSha256": version.encrypted_sha256,
        "encryptedBytes": version.encrypted_file_size,
        "contentUrl": f"/api/v1/reader/books/{book.id}/content",
    }


@router.post("/licenses/validate")
def validate_license(
    payload: dict,
    user: ReaderUser,
    db: DbSession,
) -> dict:
    token = payload.get("license")
    if not isinstance(token, str):
        raise HTTPException(422, "License is required")
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(
            __import__("base64").b64decode(license_public_key())
        )
        claims = jwt.decode(token, public_key, algorithms=["EdDSA"])
        if claims.get("sub") != str(user.id) or claims.get("typ") != "book_license":
            raise ValueError("License owner mismatch")
        license_id = _uuid(claims["book_version_id"], "book version id")
    except (jwt.PyJWTError, KeyError, ValueError) as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "License is invalid") from error
    record = db.scalar(
        select(BookLicense).where(
            BookLicense.user_id == user.id,
            BookLicense.book_version_id == license_id,
            BookLicense.protected_key_payload == token,
            BookLicense.revoked_at.is_(None),
        )
    )
    if not record or record.valid_until <= datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "License is expired or revoked")
    _device(db, user, record.device_id)
    db.commit()
    return {"valid": True, "validUntil": record.valid_until.isoformat()}


@router.get("/books/{book_id}/content", response_class=FileResponse)
def download_content(
    book_id: uuid.UUID,
    user: ReaderUser,
    db: DbSession,
    device_header: Annotated[str, Header(alias="X-Device-Id")],
) -> FileResponse:
    _device(db, user, _uuid(device_header, "device id"))
    book = _published_book(db, book_id)
    version = book.current_version
    db.add(ReadingEvent(user_id=user.id, book_id=book.id, event_type="download_completed"))
    db.commit()
    return FileResponse(
        protected_book_file(version.storage_path),
        media_type="application/octet-stream",
        filename=f"{version.id}.brc",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/library")
def library(user: ReaderUser, db: DbSession) -> dict:
    favorites = db.scalars(select(Favorite).where(Favorite.user_id == user.id)).all()
    bookmarks = db.scalars(
        select(Bookmark).where(Bookmark.user_id == user.id).order_by(Bookmark.updated_at.desc())
    ).all()
    progress = db.scalars(
        select(ReadingProgress)
        .where(ReadingProgress.user_id == user.id)
        .order_by(ReadingProgress.updated_at.desc())
    ).all()
    return {
        "favoriteBookIds": [str(item.book_id) for item in favorites],
        "bookmarks": [_bookmark_json(item) for item in bookmarks],
        "progress": [_progress_json(item) for item in progress],
    }


@router.put("/favorites/{book_id}")
def set_favorite(
    book_id: uuid.UUID, payload: FavoriteMutation, user: ReaderUser, db: DbSession
) -> dict:
    _published_book(db, book_id)
    favorite = db.get(Favorite, (user.id, book_id))
    if payload.isFavorite and not favorite:
        db.add(Favorite(user_id=user.id, book_id=book_id))
    elif not payload.isFavorite and favorite:
        db.delete(favorite)
    db.commit()
    return {"bookId": str(book_id), "isFavorite": payload.isFavorite}


@router.put("/progress/{book_id}")
def save_progress(
    book_id: uuid.UUID, payload: ProgressInput, user: ReaderUser, db: DbSession
) -> dict:
    if _uuid(payload.bookId, "book id") != book_id:
        raise HTTPException(422, "Book id mismatch")
    book = _published_book(db, book_id)
    version_id = _uuid(payload.bookVersionId, "book version id")
    if book.current_version_id != version_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Book version changed")
    device = _device(db, user, _uuid(payload.deviceId, "device id"))
    item = db.get(ReadingProgress, (user.id, book_id))
    if not item:
        item = ReadingProgress(user_id=user.id, book_id=book_id)
        db.add(item)
    item.book_version_id = version_id
    item.device_id = device.id
    item.page_number = payload.pageNumber
    item.normalized_offset = payload.normalizedOffset
    item.reader_mode = payload.readerMode
    item.percentage = payload.percentage
    item.last_read_at_client = payload.lastReadAtClient
    item.synced_at_server = utcnow()
    db.add(ReadingEvent(user_id=user.id, book_id=book_id, event_type="book_opened"))
    db.commit()
    return _progress_json(item)


@router.put("/bookmarks/{bookmark_id}")
def save_bookmark(
    bookmark_id: uuid.UUID, payload: BookmarkInput, user: ReaderUser, db: DbSession
) -> dict:
    book = _published_book(db, _uuid(payload.bookId, "book id"))
    version_id = _uuid(payload.bookVersionId, "book version id")
    if book.current_version_id != version_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Book version changed")
    item = db.get(Bookmark, bookmark_id)
    if item and item.user_id != user.id:
        raise HTTPException(404, "Bookmark not found")
    if not item:
        item = Bookmark(id=bookmark_id, user_id=user.id, book_id=book.id)
        db.add(item)
    item.book_version_id = version_id
    item.page_number = payload.pageNumber
    item.normalized_offset = payload.normalizedOffset
    item.label = payload.label
    db.commit()
    db.refresh(item)
    return _bookmark_json(item)


@router.delete("/bookmarks/{bookmark_id}", status_code=204)
def delete_bookmark(bookmark_id: uuid.UUID, user: ReaderUser, db: DbSession) -> None:
    item = db.get(Bookmark, bookmark_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Bookmark not found")
    db.delete(item)
    db.commit()
