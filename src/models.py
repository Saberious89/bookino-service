import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(160))
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="user", index=True)
    preferred_locale: Mapped[str | None] = mapped_column(String(12))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),)


class ReaderSession(Base):
    __tablename__ = "reader_sessions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str | None] = mapped_column(String(180), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Book(Base):
    __tablename__ = "books"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    cover_path: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "book_versions.id", use_alter=True, name="fk_books_current_version", ondelete="SET NULL"
        )
    )
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    category: Mapped[Category | None] = relationship()
    versions: Mapped[list["BookVersion"]] = relationship(
        back_populates="book", foreign_keys="BookVersion.book_id", cascade="all, delete-orphan"
    )
    current_version: Mapped["BookVersion | None"] = relationship(foreign_keys=[current_version_id])
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_books_status"),
        CheckConstraint(
            "publication_year IS NULL OR publication_year BETWEEN 1000 AND 3000",
            name="ck_books_year",
        ),
        CheckConstraint("page_count IS NULL OR page_count > 0", name="ck_books_pages"),
    )


class BookVersion(Base):
    __tablename__ = "book_versions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(Text, unique=True)
    container_format_version: Mapped[int] = mapped_column(Integer, default=1)
    plain_file_size: Mapped[int] = mapped_column(BigInteger)
    encrypted_file_size: Mapped[int] = mapped_column(BigInteger)
    plain_sha256: Mapped[str] = mapped_column(String(64))
    encrypted_sha256: Mapped[str] = mapped_column(String(64))
    wrapped_dek: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="ready")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    book: Mapped[Book] = relationship(back_populates="versions", foreign_keys=[book_id])
    __table_args__ = (
        UniqueConstraint("book_id", "version_number", name="uq_book_version_number"),
        CheckConstraint(
            "status IN ('processing', 'ready', 'failed', 'archived')", name="ck_versions_status"
        ),
    )


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    installation_id: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str | None] = mapped_column(String(160))
    public_key: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()
    __table_args__ = (
        UniqueConstraint("user_id", "installation_id", name="uq_device_installation"),
    )


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Bookmark(Base):
    __tablename__ = "bookmarks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    book_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("book_versions.id", ondelete="CASCADE")
    )
    page_number: Mapped[int] = mapped_column(Integer)
    normalized_offset: Mapped[float | None] = mapped_column(Float)
    label: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
    )
    book_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("book_versions.id", ondelete="CASCADE")
    )
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    page_number: Mapped[int] = mapped_column(Integer)
    normalized_offset: Mapped[float | None] = mapped_column(Float)
    reader_mode: Mapped[str | None] = mapped_column(String(40))
    percentage: Mapped[float | None] = mapped_column(Float)
    last_read_at_client: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at_server: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BookLicense(Base):
    __tablename__ = "book_licenses"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    book_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    book_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("book_versions.id", ondelete="CASCADE")
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    license_version: Mapped[int] = mapped_column(Integer, default=1)
    protected_key_payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReadingEvent(Base):
    __tablename__ = "reading_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


Index("ix_progress_recent", ReadingProgress.user_id, ReadingProgress.updated_at)
Index("ix_active_devices", Device.user_id, Device.revoked_at)
