import base64
from collections.abc import Generator

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db import Base, get_db
from src.main import app
from src.reader_security import protect_dek_for_device


def _public_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def test_protect_dek_uses_required_rsa_oaep_parameters() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    dek = b"0123456789abcdef0123456789abcdef"

    protected_dek = protect_dek_for_device(dek, public_key)

    assert private_key.decrypt(
        base64.b64decode(protected_dek),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    ) == dek


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
