import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload

from .config import settings
from .models import (
    AdminAuditLog,
    Book,
    BookVersion,
    Category,
    Device,
    ReadingEvent,
    User,
    utcnow,
)
from .schemas import BookInput, CategoryInput, Credentials
from .security import (
    AdminUser,
    DbSession,
    clear_session_cookie,
    hash_password,
    optional_user,
    set_session_cookie,
    verify_password,
)
from .storage import cover_file, encrypt_pdf, protected_book_file, store_cover

app = FastAPI(title="Protected Book API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.admin_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Requested-With"],
)


def _uuid(value: str | None, field: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise HTTPException(422, f"Invalid {field}") from error


def _audit(db: DbSession, actor: User, action: str, target_type: str, target_id: object) -> None:
    db.add(
        AdminAuditLog(
            actor_user_id=actor.id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
        )
    )


def _book_json(book: Book) -> dict:
    version = book.current_version
    return {
        "id": str(book.id),
        "title": book.title,
        "author": book.author,
        "description": book.description,
        "categoryId": str(book.category_id) if book.category_id else None,
        "publicationYear": book.publication_year,
        "pageCount": book.page_count,
        "coverUrl": f"/api/v1/media/{book.cover_path}" if book.cover_path else None,
        "pdfName": version.original_filename if version else None,
        "pdfBytes": version.plain_file_size if version else None,
        "status": book.status,
        "version": version.version_number if version else 1,
        "createdAt": book.created_at.isoformat(),
    }


async def _legacy_book_metadata(request: Request) -> str | None:
    """Read the former JSON form field without advertising it in OpenAPI."""
    value = (await request.form()).get("metadata")
    return value if isinstance(value, str) else None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/auth/status")
def auth_status(db: DbSession, user: Annotated[User | None, Depends(optional_user)]) -> dict:
    has_admin = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) > 0
    return {
        "hasAdmin": has_admin,
        "authenticated": bool(user and user.role == "admin"),
        "username": user.username if user and user.role == "admin" else None,
    }


@app.post("/api/v1/auth/bootstrap-admin", status_code=201)
def bootstrap_admin(credentials: Credentials, response: Response, db: DbSession) -> dict:
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(72819421)"))
    if db.scalar(select(func.count()).select_from(User).where(User.role == "admin")):
        raise HTTPException(status.HTTP_409_CONFLICT, "Admin already exists")
    if db.scalar(select(User).where(User.username == credentials.username.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    user = User(
        username=credentials.username.strip(),
        display_name=credentials.username.strip(),
        password_hash=hash_password(credentials.password),
        role="admin",
    )
    db.add(user)
    for order, name in enumerate(("داستان", "هنر و طراحی", "تاریخ", "علمی")):
        db.add(Category(name=name, sort_order=order))
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)
    return {"username": user.username}


@app.post("/api/v1/auth/login")
def login(credentials: Credentials, response: Response, db: DbSession) -> dict:
    user = db.scalar(select(User).where(User.username == credentials.username.strip()))
    if (
        not user
        or user.role != "admin"
        or not user.is_active
        or not verify_password(credentials.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    user.last_active_at = utcnow()
    db.commit()
    set_session_cookie(response, user)
    return {"username": user.username}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(response: Response) -> None:
    clear_session_cookie(response)


@app.get("/api/v1/media/{path:path}")
def media(path: str) -> FileResponse:
    return FileResponse(cover_file(path), headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/v1/catalog")
def public_catalog(db: DbSession) -> list[dict]:
    books = db.scalars(
        select(Book)
        .where(Book.status == "published")
        .options(joinedload(Book.current_version))
        .order_by(Book.created_at.desc())
    ).all()
    return [_book_json(book) for book in books if book.current_version]


@app.get("/api/v1/admin/snapshot")
def admin_snapshot(_: AdminUser, db: DbSession) -> dict:
    books = db.scalars(
        select(Book).options(joinedload(Book.current_version)).order_by(Book.created_at.desc())
    ).all()
    categories = db.scalars(select(Category).order_by(Category.sort_order, Category.name)).all()
    users = db.scalars(
        select(User).where(User.role == "user").order_by(User.created_at.desc())
    ).all()
    devices = db.scalars(
        select(Device).options(joinedload(Device.user)).order_by(Device.last_seen_at.desc())
    ).all()
    return {
        "books": [_book_json(book) for book in books],
        "categories": [
            {"id": str(item.id), "name": item.name, "isActive": item.is_active}
            for item in categories
        ],
        "users": [
            {
                "id": str(item.id),
                "name": item.display_name or item.username,
                "joinedAt": item.created_at.isoformat(),
                "lastActive": item.last_active_at.isoformat(),
            }
            for item in users
        ],
        "devices": [
            {
                "id": str(item.id),
                "userName": item.user.display_name or item.user.username,
                "label": item.display_name or "Android",
                "platform": item.platform,
                "lastSeen": item.last_seen_at.isoformat(),
                "isRevoked": item.revoked_at is not None,
            }
            for item in devices
        ],
    }


@app.post("/api/v1/admin/books")
def save_book(
    actor: AdminUser,
    db: DbSession,
    legacy_metadata: Annotated[str | None, Depends(_legacy_book_metadata)],
    id: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
    author: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    category_id: Annotated[str | None, Form(alias="categoryId")] = None,
    publication_year: Annotated[int | None, Form(alias="publicationYear")] = None,
    page_count: Annotated[int | None, Form(alias="pageCount")] = None,
    book_status: Annotated[str | None, Form(alias="status")] = None,
    cover: Annotated[UploadFile | None, File()] = None,
    pdf: Annotated[UploadFile | None, File()] = None,
) -> dict:
    if legacy_metadata is not None:
        try:
            payload = BookInput.model_validate(json.loads(legacy_metadata))
        except (json.JSONDecodeError, ValueError) as error:
            raise HTTPException(422, "Invalid book metadata") from error
        book_id = _uuid(payload.id, "book id")
    else:
        book_id = _uuid(id, "book id")

    book = db.get(Book, book_id) if book_id else None
    if book_id and not book:
        raise HTTPException(404, "Book not found")

    if legacy_metadata is None:
        try:
            payload = BookInput(
                id=id,
                title=title if title is not None else (book.title if book else "Untitled"),
                author=author,
                description=description,
                categoryId=category_id,
                publicationYear=publication_year,
                pageCount=page_count,
                status=(
                    book_status if book_status is not None else (book.status if book else "draft")
                ),
            )
        except ValueError as error:
            raise HTTPException(422, "Invalid book metadata") from error

    if not book:
        book = Book(title=payload.title)
        db.add(book)
        db.flush()

    category_id = _uuid(payload.categoryId, "category id")
    if category_id and not db.get(Category, category_id):
        raise HTTPException(422, "Category not found")
    book.title = payload.title.strip()
    book.author = payload.author.strip() if payload.author else None
    book.description = payload.description.strip() if payload.description else None
    book.category_id = category_id
    book.publication_year = payload.publicationYear
    book.page_count = payload.pageCount

    if cover:
        book.cover_path = store_cover(cover, book.id)
    if pdf:
        next_number = (
            db.scalar(
                select(func.coalesce(func.max(BookVersion.version_number), 0)).where(
                    BookVersion.book_id == book.id
                )
            )
            + 1
        )
        version_id = uuid.uuid4()
        encrypted = encrypt_pdf(pdf, version_id)
        version = BookVersion(
            id=version_id,
            book_id=book.id,
            version_number=next_number,
            original_filename=Path(pdf.filename or "book.pdf").name,
            storage_path=encrypted.storage_path,
            plain_file_size=encrypted.plain_size,
            encrypted_file_size=encrypted.encrypted_size,
            plain_sha256=encrypted.plain_sha256,
            encrypted_sha256=encrypted.encrypted_sha256,
            wrapped_dek=encrypted.wrapped_dek,
            status="ready",
            created_by=actor.id,
            published_at=utcnow() if payload.status == "published" else None,
        )
        db.add(version)
        db.flush()
        book.current_version_id = version.id
    if payload.status == "published" and not book.current_version_id:
        raise HTTPException(422, "A ready PDF version is required before publishing")
    book.status = payload.status
    _audit(db, actor, "save_book", "book", book.id)
    db.commit()
    db.refresh(book)
    book = db.scalar(
        select(Book).where(Book.id == book.id).options(joinedload(Book.current_version))
    )
    return _book_json(book)


@app.post("/api/v1/admin/books/{book_id}/archive", status_code=204)
def archive_book(book_id: uuid.UUID, actor: AdminUser, db: DbSession) -> None:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    book.status = "archived"
    _audit(db, actor, "archive_book", "book", book.id)
    db.commit()


@app.get(
    "/api/v1/admin/books/{book_id}/protected-file",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "The encrypted BRC book container",
        }
    },
)
def download_protected_book(book_id: uuid.UUID, actor: AdminUser, db: DbSession) -> FileResponse:
    book = db.scalar(
        select(Book).where(Book.id == book_id).options(joinedload(Book.current_version))
    )
    if not book:
        raise HTTPException(404, "Book not found")
    if not book.current_version:
        raise HTTPException(404, "Book has no protected file")

    version = book.current_version
    path = protected_book_file(version.storage_path)
    _audit(db, actor, "download_protected_book", "book_version", version.id)
    db.commit()

    filename = f"{Path(version.original_filename).stem}.brc"
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.put("/api/v1/admin/categories/{category_id}")
def save_category(
    category_id: uuid.UUID, payload: CategoryInput, actor: AdminUser, db: DbSession
) -> dict:
    category = db.get(Category, category_id)
    if not category:
        category = Category(id=category_id, name=payload.name.strip())
        db.add(category)
    category.name = payload.name.strip()
    category.is_active = payload.isActive
    _audit(db, actor, "save_category", "category", category.id)
    db.commit()
    return {"id": str(category.id), "name": category.name, "isActive": category.is_active}


@app.post("/api/v1/admin/categories", status_code=201)
def create_category(payload: CategoryInput, actor: AdminUser, db: DbSession) -> dict:
    category = Category(name=payload.name.strip(), is_active=payload.isActive)
    db.add(category)
    db.flush()
    _audit(db, actor, "create_category", "category", category.id)
    db.commit()
    return {"id": str(category.id), "name": category.name, "isActive": category.is_active}


@app.post("/api/v1/admin/devices/{device_id}/revoke", status_code=204)
def revoke_device(device_id: uuid.UUID, actor: AdminUser, db: DbSession) -> None:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.revoked_at:
        device.revoked_at = datetime.now(UTC)
    _audit(db, actor, "revoke_device", "device", device.id)
    db.commit()


@app.get("/api/v1/admin/analytics")
def analytics(_: AdminUser, db: DbSession) -> dict:
    event_counts = dict(
        db.execute(
            select(ReadingEvent.event_type, func.count()).group_by(ReadingEvent.event_type)
        ).all()
    )
    return {
        "totalBooks": db.scalar(select(func.count()).select_from(Book)),
        "publishedBooks": db.scalar(
            select(func.count()).select_from(Book).where(Book.status == "published")
        ),
        "readers": db.scalar(select(func.count()).select_from(User).where(User.role == "user")),
        "activeDevices": db.scalar(
            select(func.count()).select_from(Device).where(Device.revoked_at.is_(None))
        ),
        "events": event_counts,
    }
