import base64
import hashlib
import json
import math
import os
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, UploadFile, status

from .config import settings

MAGIC = b"BRC1"
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class EncryptedBook:
    storage_path: str
    plain_size: int
    encrypted_size: int
    plain_sha256: str
    encrypted_sha256: str
    wrapped_dek: str


def _safe_suffix(filename: str | None, fallback: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else fallback


def store_cover(upload: UploadFile, book_id: uuid.UUID) -> str:
    data = upload.file.read(settings.max_cover_bytes + 1)
    if not data or len(data) > settings.max_cover_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Cover is empty or too large")
    valid = (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or data.startswith((b"RIFF",))
        and data[8:12] == b"WEBP"
    )
    if not valid:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Cover must be PNG, JPEG, or WebP"
        )
    relative = (
        Path("covers") / str(book_id) / f"{uuid.uuid4().hex}{_safe_suffix(upload.filename, '.img')}"
    )
    target = settings.storage_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative.as_posix()


def encrypt_pdf(upload: UploadFile, version_id: uuid.UUID) -> EncryptedBook:
    source = upload.file
    source.seek(0, os.SEEK_END)
    plain_size = source.tell()
    if plain_size <= 5 or plain_size > settings.max_pdf_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF is empty or too large")
    source.seek(0)
    if not source.read(5).startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a PDF")
    source.seek(0)

    relative = Path("protected-books") / f"{version_id}.brc"
    target = settings.storage_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    dek = AESGCM.generate_key(bit_length=256)
    cipher = AESGCM(dek)
    header = json.dumps(
        {
            "format": 1,
            "book_version_id": str(version_id),
            "plain_length": plain_size,
            "chunk_size": CHUNK_SIZE,
            "chunk_count": math.ceil(plain_size / CHUNK_SIZE),
            "cipher": "AES-256-GCM",
        },
        separators=(",", ":"),
    ).encode()
    plain_digest = hashlib.sha256()
    encrypted_digest = hashlib.sha256()

    try:
        with target.open("wb") as output:
            prefix = MAGIC + struct.pack(">I", len(header)) + header
            output.write(prefix)
            encrypted_digest.update(prefix)
            index = 0
            while chunk := source.read(CHUNK_SIZE):
                plain_digest.update(chunk)
                nonce = os.urandom(12)
                aad = f"{version_id}:{index}".encode()
                encrypted = cipher.encrypt(nonce, chunk, aad)
                record = struct.pack(">I", len(encrypted)) + nonce + encrypted
                output.write(record)
                encrypted_digest.update(record)
                index += 1
    except Exception:
        target.unlink(missing_ok=True)
        raise

    wrap_nonce = os.urandom(12)
    wrapped = AESGCM(settings.book_kek).encrypt(wrap_nonce, dek, str(version_id).encode())
    wrapped_dek = base64.b64encode(wrap_nonce + wrapped).decode()
    return EncryptedBook(
        storage_path=relative.as_posix(),
        plain_size=plain_size,
        encrypted_size=target.stat().st_size,
        plain_sha256=plain_digest.hexdigest(),
        encrypted_sha256=encrypted_digest.hexdigest(),
        wrapped_dek=wrapped_dek,
    )


def cover_file(path: str) -> Path:
    candidate = (settings.storage_root / path).resolve()
    cover_root = (settings.storage_root / "covers").resolve()
    if cover_root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cover not found")
    return candidate


def protected_book_file(path: str) -> Path:
    candidate = (settings.storage_root / path).resolve()
    protected_root = (settings.storage_root / "protected-books").resolve()
    if protected_root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Protected book file not found")
    return candidate


def unwrap_dek(wrapped_dek: str, version_id: uuid.UUID) -> bytes:
    try:
        payload = base64.b64decode(wrapped_dek, validate=True)
        if len(payload) < 29:
            raise ValueError("Wrapped key is too short")
        return AESGCM(settings.book_kek).decrypt(
            payload[:12], payload[12:], str(version_id).encode()
        )
    except (ValueError, TypeError) as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Book key cannot be unlocked"
        ) from error
