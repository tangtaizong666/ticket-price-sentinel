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


def test_windows_portable_build_script_exists_and_defines_layout() -> None:
    script = Path("scripts/build_windows_portable.ps1")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "FlyTicket-Windows" in content
    assert '"python"' in content
    assert '"ms-playwright"' in content
    assert "launch_portable.bat" in content
    assert "Compress-Archive" in content


def test_windows_portable_build_script_excludes_user_state() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    assert ".env" in content
    assert "data" in content
    assert "playwright-profile" in content
    assert "requirements-dev.txt" in content


def test_windows_portable_build_downloads_are_staged_outside_package() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    assert re.search(
        r'\$downloadsRoot\s*=\s*Join-Path\s+\$distRootPath\s+"_downloads"',
        content,
        re.IGNORECASE,
    )
    assert not re.search(
        r'\$downloadsRoot\s*=\s*Join-Path\s+\$packageRoot\s+"_downloads"',
        content,
        re.IGNORECASE,
    )


def test_windows_portable_build_script_maps_launcher_to_package_root() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    assert re.search(
        r'Copy-RequiredItem\s+-Source\s+\(Join-Path\s+\$repoRoot\s+"scripts[/\\]launch_portable\.bat"\)\s+'
        r'-Destination\s+\(Join-Path\s+\$packageRoot\s+"启动机票监控\.bat"\)',
        content,
    )


def test_windows_portable_build_script_does_not_copy_local_state_to_package() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    forbidden_package_copies = [
        ".env",
        ".venv",
        "requirements-dev.txt",
        "data",
        "playwright-profile",
        "app.db",
        "_downloads",
    ]
    for name in forbidden_package_copies:
        assert not re.search(
            rf'Copy-\w+Item\s+-Source\s+\(Join-Path\s+\$repoRoot\s+"{re.escape(name)}"\)',
            content,
        )

    assert re.search(
        r'\$dataRoot\s*=\s*Join-Path\s+\$packageRoot\s+"data"',
        content,
        re.IGNORECASE,
    )
    assert re.search(
        r'New-Item\s+-ItemType\s+Directory\s+-Force\s+-Path\s+\$dataRoot',
        content,
        re.IGNORECASE,
    )
    assert re.search(
        r'Compress-Archive\s+-Path\s+\(Join-Path\s+\$packageRoot\s+"\*"\)',
        content,
        re.IGNORECASE,
    )


def test_windows_portable_build_script_removes_nested_python_cache_files() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    assert re.search(
        r'Get-ChildItem\s+-LiteralPath\s+\$packageRoot\s+-Recurse\s+-Directory\s+-Filter\s+"__pycache__"',
        content,
        re.IGNORECASE,
    )
    assert re.search(
        r'Get-ChildItem\s+-LiteralPath\s+\$packageRoot\s+-Recurse\s+-File\s+-Include\s+"\*\.pyc",\s+"\*\.pyo"',
        content,
        re.IGNORECASE,
    )
