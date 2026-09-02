import io
import json
import struct
import uuid

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import UploadFile

from src.config import settings
from src.storage import MAGIC, encrypt_pdf


def _decrypt_first_chunk(path, version_id, wrapped_dek):
    import base64

    wrapped = base64.b64decode(wrapped_dek)
    dek = AESGCM(settings.book_kek).decrypt(wrapped[:12], wrapped[12:], str(version_id).encode())
    with path.open("rb") as source:
        assert source.read(4) == MAGIC
        header = json.loads(source.read(struct.unpack(">I", source.read(4))[0]))
        encrypted_length = struct.unpack(">I", source.read(4))[0]
        nonce = source.read(12)
        encrypted = source.read(encrypted_length)
    plain = AESGCM(dek).decrypt(nonce, encrypted, f"{version_id}:0".encode())
    return header, plain


def test_encrypts_pdf_as_random_access_container(tmp_path):
    original_root = settings.storage_root
    object.__setattr__(settings, "storage_root", tmp_path)
    version_id = uuid.uuid4()
    content = b"%PDF-1.7\n" + b"protected-content" * 100
    try:
        result = encrypt_pdf(UploadFile(filename="book.pdf", file=io.BytesIO(content)), version_id)
        target = tmp_path / result.storage_path
        assert target.read_bytes()[:4] == MAGIC
        assert content not in target.read_bytes()
        header, decrypted = _decrypt_first_chunk(target, version_id, result.wrapped_dek)
        assert header["book_version_id"] == str(version_id)
        assert decrypted == content
    finally:
        object.__setattr__(settings, "storage_root", original_root)


def test_modified_ciphertext_is_rejected(tmp_path):
    original_root = settings.storage_root
    object.__setattr__(settings, "storage_root", tmp_path)
    version_id = uuid.uuid4()
    try:
        result = encrypt_pdf(
            UploadFile(filename="book.pdf", file=io.BytesIO(b"%PDF-1.7\nsecret")), version_id
        )
        target = tmp_path / result.storage_path
        data = bytearray(target.read_bytes())
        data[-1] ^= 1
        target.write_bytes(data)
        with pytest.raises(InvalidTag):
            _decrypt_first_chunk(target, version_id, result.wrapped_dek)
    finally:
        object.__setattr__(settings, "storage_root", original_root)
