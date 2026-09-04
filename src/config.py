import base64
import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://book_reader:book_reader@localhost:5432/book_reader"
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "development-only-change-me-32-bytes")
    storage_root: Path = Path(os.getenv("STORAGE_ROOT", "./data/storage"))
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    max_pdf_bytes: int = int(os.getenv("MAX_PDF_BYTES", str(200 * 1024 * 1024)))
    max_cover_bytes: int = int(os.getenv("MAX_COVER_BYTES", str(2 * 1024 * 1024)))
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
    offline_license_days: int = int(os.getenv("OFFLINE_LICENSE_DAYS", "7"))
    google_client_ids_raw: str = os.getenv("GOOGLE_CLIENT_IDS", "")

    def __post_init__(self) -> None:
        if self.environment == "production" and (
            self.jwt_secret == "development-only-change-me-32-bytes" or len(self.jwt_secret) < 32
        ):
            raise RuntimeError("JWT_SECRET must be a unique secret of at least 32 characters")

    @cached_property
    def admin_origins(self) -> list[str]:
        raw = os.getenv("ADMIN_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
        return [value.strip() for value in raw.split(",") if value.strip()]

    @cached_property
    def book_kek(self) -> bytes:
        raw = os.getenv("BOOK_KEK_BASE64")
        if not raw:
            if self.environment == "production":
                raise RuntimeError("BOOK_KEK_BASE64 is required in production")
            return bytes.fromhex("01" * 32)
        value = base64.b64decode(raw, validate=True)
        if len(value) != 32:
            raise RuntimeError("BOOK_KEK_BASE64 must decode to exactly 32 bytes")
        return value

    @cached_property
    def google_client_ids(self) -> list[str]:
        return [value.strip() for value in self.google_client_ids_raw.split(",") if value.strip()]


settings = Settings()
