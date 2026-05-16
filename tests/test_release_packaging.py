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
    assert "CTRIP_SNAPSHOT_DIR=data/debug" in content
    assert "CTRIP_SAVE_DEBUG_SNAPSHOT=0" in content
    assert "CTRIP_DEBUG_SNAPSHOT_DIR=data/debug" in content
    assert "MONITOR_REALERT_COOLDOWN_ENABLED=1" in content
    assert "MONITOR_FAILURE_BACKOFF_MINUTES=5" in content
    assert "CTRIP_AUTO_RELOGIN_COOLDOWN_MINUTES=30" in content


def test_settings_exposes_app_base_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:8123")

    from app.settings import Settings

    settings = Settings()

    assert settings.app_base_url == "http://127.0.0.1:8123"


def test_settings_exposes_debug_snapshot_and_auto_relogin_config(monkeypatch) -> None:
    monkeypatch.setenv("CTRIP_SAVE_DEBUG_SNAPSHOT", "1")
    monkeypatch.setenv("CTRIP_DEBUG_SNAPSHOT_DIR", "data/custom-debug")
    monkeypatch.setenv("MONITOR_REALERT_COOLDOWN_ENABLED", "0")
    monkeypatch.setenv("MONITOR_FAILURE_BACKOFF_MINUTES", "7")
    monkeypatch.setenv("CTRIP_AUTO_RELOGIN_COOLDOWN_MINUTES", "45")

    from app.settings import Settings

    settings = Settings()

    assert settings.ctrip_save_debug_snapshot is True
    assert settings.ctrip_debug_snapshot_dir == Path.cwd() / "data/custom-debug"
    assert settings.monitor_realert_cooldown_enabled is False
    assert settings.monitor_failure_backoff_minutes == 7
    assert settings.ctrip_auto_relogin_cooldown_minutes == 45


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
        r'-Destination\s+\(Join-Path\s+\$packageRoot\s+\$portableLauncherName\)',
        content,
    )
    assert "0x542f" in content
    assert "0x52a8" in content


def test_windows_portable_build_script_avoids_non_ascii_release_filenames() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    assert '"启动机票监控.bat"' not in content
    assert '"README_使用说明.txt"' not in content
    assert "$portableLauncherName" in content
    assert "$releaseReadmeName" in content


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
        r'\$_.Extension\s+-in\s+@\(.*"\.pyc".*"\.pyo".*\)',
        content,
        re.IGNORECASE,
    )
    assert not re.search(
        r'Get-ChildItem\s+-LiteralPath\s+\$packageRoot\s+-Recurse\s+-File\s+-Include',
        content,
        re.IGNORECASE,
    )


def test_windows_portable_build_script_verifies_download_hashes() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    assert "[string]$PythonZipSha256" in content
    assert "[string]$GetPipSha256" in content
    assert "8D3F33BE9EB810F23C102F08475AF2854E50484B8E4E06275E937BE61CE3D2FB" in content
    assert "66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76" in content
    assert "Get-FileHash" in content
    assert "Assert-FileSha256" in content
    assert content.index("Invoke-WebRequest -Uri $pythonZipUrl -OutFile $pythonZip") < content.index(
        'Assert-FileSha256 -Path $pythonZip -ExpectedSha256 $PythonZipSha256'
    )
    assert content.index('Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip') < content.index(
        'Assert-FileSha256 -Path $getPip -ExpectedSha256 $GetPipSha256'
    )


def test_gitignore_ignores_all_runtime_data_except_placeholder() -> None:
    content = Path(".gitignore").read_text(encoding="utf-8")

    assert "/data/*" in content
    assert "!/data/.gitkeep" in content
    assert "/data/playwright-profile/" not in content
    assert "/data/*.html" not in content


def test_release_user_readme_exists_and_avoids_developer_jargon() -> None:
    content = Path("README_使用说明.txt").read_text(encoding="utf-8")

    assert "双击" in content
    assert "启动机票监控.bat" in content
    assert "登录携程" in content
    assert "pip" not in content.lower()
    assert "virtualenv" not in content.lower()


def test_project_readme_mentions_windows_release_and_build_script() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "FlyTicket-Windows" in content
    assert "启动机票监控.bat" in content
    assert "scripts/build_windows_portable.ps1" in content


def test_project_readme_mentions_source_zip_click_to_run_path() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "Code → Download ZIP" in content
    assert "start_fly_ticket.bat" in content
    assert "首次运行会联网下载内置 Python" in content
    assert "不需要提前安装 Python" in content


def test_project_readme_highlights_chinese_user_and_developer_paths() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "机票监控工作台" in content
    assert "普通用户路径" in content
    assert "开发者路径" in content
    assert "问题排查" in content


def test_project_readme_has_windows_and_unix_manual_commands() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "Windows PowerShell" in content
    assert ".\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt" in content
    assert ".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000" in content
    assert "macOS / Linux" in content
    assert ".venv/bin/python -m pip install -r requirements-dev.txt" in content


def test_github_actions_ci_runs_release_hygiene_checks_without_building_portable_package() -> None:
    content = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python -m pip check" in content
    assert "python -m compileall -q app scripts" in content
    assert "python -m pytest -q" in content
    assert "scripts/build_windows_portable.ps1" not in content
    assert "playwright install" not in content


def test_ctrip_fixture_does_not_contain_obvious_live_session_material() -> None:
    content = Path("tests/fixtures/ctrip_search_results.html").read_text(
        encoding="utf-8"
    ).lower()

    forbidden_markers = [
        "cookie",
        "set-cookie",
        "passport",
        "ubt_trace_id",
        "sessionid",
        "authorization",
        "csrf",
    ]
    for marker in forbidden_markers:
        assert marker not in content
