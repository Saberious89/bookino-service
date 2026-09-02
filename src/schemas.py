from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=200)


class BookInput(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=300)
    description: str | None = None
    categoryId: str | None = None
    publicationYear: int | None = Field(default=None, ge=1000, le=3000)
    pageCount: int | None = Field(default=None, ge=1)
    status: str = Field(pattern="^(draft|published|archived)$")


class CategoryInput(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=160)
    isActive: bool = True
