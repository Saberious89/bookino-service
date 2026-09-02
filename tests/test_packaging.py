import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_requirements_matches_runtime_dependencies() -> None:
    requirements_path = PROJECT_ROOT / "requirements.txt"
    assert requirements_path.is_file(), "requirements.txt is required by hosted builders"

    requirements = {
        line.strip()
        for line in requirements_path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        runtime_dependencies = set(tomllib.load(pyproject_file)["project"]["dependencies"])

    assert requirements == runtime_dependencies


def test_save_book_openapi_exposes_nullable_form_fields() -> None:
    from src.main import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/admin/books"]["post"]
    body_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    if "$ref" in body_schema:
        body_schema = schema["components"]["schemas"][body_schema["$ref"].rsplit("/", 1)[-1]]

    properties = body_schema["properties"]
    assert {
        "id",
        "title",
        "author",
        "description",
        "categoryId",
        "publicationYear",
        "pageCount",
        "status",
        "cover",
        "pdf",
    } <= properties.keys()
    assert "metadata" not in properties
    assert body_schema.get("required", []) == []
