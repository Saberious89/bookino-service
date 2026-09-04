from collections.abc import Generator

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db import Base, get_db
from src.main import app


def _public_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def test_reader_register_login_and_device_limit(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'reader.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            registered = client.post(
                "/api/v1/reader/auth/register",
                json={
                    "email": "reader@example.com",
                    "password": "reader-password",
                    "displayName": "Reader",
                },
            )
            assert registered.status_code == 201, registered.text
            auth = {"Authorization": f"Bearer {registered.json()['accessToken']}"}
            assert client.get("/api/v1/reader/me", headers=auth).status_code == 200

            for index in range(3):
                device = client.post(
                    "/api/v1/reader/devices",
                    headers=auth,
                    json={
                        "installationId": f"installation-{index}",
                        "platform": "android",
                        "displayName": f"Android {index}",
                        "publicKey": _public_key(),
                        "appVersion": "1.0.0",
                    },
                )
                assert device.status_code == 200, device.text

            fourth = client.post(
                "/api/v1/reader/devices",
                headers=auth,
                json={
                    "installationId": "installation-4",
                    "platform": "android",
                    "displayName": "Fourth Android",
                    "publicKey": _public_key(),
                },
            )
            assert fourth.status_code == 409
            assert fourth.json()["detail"] == "Device limit reached"

            login = client.post(
                "/api/v1/reader/auth/login",
                json={"email": "reader@example.com", "password": "reader-password"},
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["email"] == "reader@example.com"
    finally:
        app.dependency_overrides.clear()
