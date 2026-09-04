from datetime import datetime

from pydantic import BaseModel, Field


class ReaderRegistration(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    displayName: str | None = Field(default=None, max_length=160)


class ReaderLogin(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=200)


class GoogleLogin(BaseModel):
    idToken: str = Field(min_length=20)


class RefreshRequest(BaseModel):
    refreshToken: str = Field(min_length=20)


class DeviceRegistration(BaseModel):
    installationId: str = Field(min_length=8, max_length=200)
    platform: str = Field(pattern="^android$")
    displayName: str | None = Field(default=None, max_length=160)
    publicKey: str = Field(min_length=100, max_length=10000)
    appVersion: str | None = Field(default=None, max_length=80)


class FavoriteMutation(BaseModel):
    isFavorite: bool


class BookmarkInput(BaseModel):
    id: str | None = None
    bookId: str
    bookVersionId: str
    pageNumber: int = Field(ge=0)
    normalizedOffset: float | None = Field(default=None, ge=0, le=1)
    label: str | None = Field(default=None, max_length=300)


class ProgressInput(BaseModel):
    bookId: str
    bookVersionId: str
    deviceId: str
    pageNumber: int = Field(ge=0)
    normalizedOffset: float | None = Field(default=None, ge=0, le=1)
    readerMode: str | None = Field(default="vertical", max_length=40)
    percentage: float | None = Field(default=None, ge=0, le=1)
    lastReadAtClient: datetime | None = None


class LocaleInput(BaseModel):
    locale: str = Field(pattern="^(fa|en)$")
