import json
import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="requires a migrated disposable PostgreSQL database"
)


def test_admin_bootstrap_publish_replace_and_archive():
    from src.main import app

    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/admin/snapshot").status_code == 401

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/bootstrap-admin",
            json={"username": "integration-admin", "password": "a-secure-test-password"},
        )
        assert response.status_code == 201, response.text

        snapshot = client.get("/api/v1/admin/snapshot")
        assert snapshot.status_code == 200
        assert len(snapshot.json()["categories"]) == 4

        metadata = {
            "title": "کتاب آزمایشی",
            "author": None,
            "description": None,
            "categoryId": None,
            "publicationYear": 2026,
            "pageCount": 1,
            "status": "published",
        }
        created = client.post(
            "/api/v1/admin/books",
            data={key: value for key, value in metadata.items() if value is not None},
            files={"pdf": ("test.pdf", b"%PDF-1.7\nprotected test payload", "application/pdf")},
        )
        assert created.status_code == 200, created.text
        book = created.json()
        assert book["version"] == 1

        protected_download = client.get(
            f"/api/v1/admin/books/{book['id']}/protected-file"
        )
        assert protected_download.status_code == 200, protected_download.text
        assert protected_download.headers["content-type"] == "application/octet-stream"
        assert protected_download.headers["cache-control"] == "private, no-store"
        assert 'filename="test.brc"' in protected_download.headers["content-disposition"]
        assert protected_download.content.startswith(b"BRC1")
        assert b"protected test payload" not in protected_download.content
        assert (
            anonymous.get(f"/api/v1/admin/books/{book['id']}/protected-file").status_code == 401
        )

        catalog = anonymous.get("/api/v1/catalog")
        assert catalog.status_code == 200
        assert len(catalog.json()) == 1
        assert "storage_path" not in catalog.text
        assert "wrapped_dek" not in catalog.text

        metadata["id"] = book["id"]
        replaced = client.post(
            "/api/v1/admin/books",
            data={"metadata": json.dumps(metadata)},
            files={"pdf": ("test-v2.pdf", b"%PDF-1.7\nsecond payload", "application/pdf")},
        )
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["version"] == 2

        archived = client.post(f"/api/v1/admin/books/{book['id']}/archive")
        assert archived.status_code == 204
        assert anonymous.get("/api/v1/catalog").json() == []
