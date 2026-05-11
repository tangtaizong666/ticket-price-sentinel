from pathlib import Path
import re


def _requirement_names(path: str) -> set[str]:
    names: set[str] = set()
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(match.group(1).lower())
    return names


def _requirement_includes(path: str) -> set[str]:
    includes: set[str] = set()
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line.startswith("-r "):
            includes.add(line.removeprefix("-r ").strip())
    return includes


def test_runtime_requirements_do_not_include_test_tools() -> None:
    runtime = _requirement_names("requirements.txt")

    assert "pytest" not in runtime
    assert "httpx" not in runtime


def test_requirement_names_parse_common_specifier_forms(tmp_path: Path) -> None:
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text(
        "\n".join(
            [
                "pytest>=8",
                "HTTPX~=0.28",
                "FastAPI[standard] ; python_version >= '3.11'",
                "Pydantic # inline comment",
                "beautifulsoup4==4.12.3",
            ]
        ),
        encoding="utf-8",
    )

    assert _requirement_names(str(requirements_file)) == {
        "pytest",
        "httpx",
        "fastapi",
        "pydantic",
        "beautifulsoup4",
    }


def test_development_requirements_include_test_tools() -> None:
    dev = _requirement_names("requirements-dev.txt")

    assert "pytest" in dev
    assert "httpx" in dev


def test_development_requirements_include_runtime_requirements_file() -> None:
    includes = _requirement_includes("requirements-dev.txt")

    assert "requirements.txt" in includes


def test_env_example_includes_portable_browser_path() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSERS_PATH=runtime/ms-playwright" in content


def test_settings_exposes_app_base_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:8123")

    from app.settings import Settings

    settings = Settings()

    assert settings.app_base_url == "http://127.0.0.1:8123"
