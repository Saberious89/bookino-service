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
