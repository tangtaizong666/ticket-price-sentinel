from pathlib import Path


def test_source_startup_script_keeps_errors_visible() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert "pause" in content.lower()
    assert "Fly Ticket" in content


def test_source_startup_script_uses_development_environment() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert ".venv\\Scripts\\python.exe" in content
    assert "requirements-dev.txt" in content
    assert "playwright install chromium" in content.lower()
    assert "runtime\\python\\python.exe" not in content


def test_source_startup_script_copies_env_before_installing_browser() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    env_copy_index = content.index('copy ".env.example" ".env"')
    playwright_install_index = content.lower().index("playwright install chromium")

    assert env_copy_index < playwright_install_index


def test_source_startup_script_delays_browser_open_until_server_starts() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")
    lower_content = content.lower()
    lines = [line.strip().lower() for line in content.splitlines()]

    assert "timeout /t" in lower_content
    assert 'start "" cmd /c' in lower_content
    assert 'start "" http://127.0.0.1:8000' not in lines


def test_portable_launcher_uses_bundled_python_only() -> None:
    script = Path("scripts/launch_portable.bat")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "runtime\\python\\python.exe" in content
    assert "where python" not in content.lower()
    assert "where py" not in content.lower()
    assert "pip install" not in content.lower()
    assert "playwright install" not in content.lower()


def test_portable_launcher_sets_browser_path_and_finds_port() -> None:
    content = Path("scripts/launch_portable.bat").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSERS_PATH" in content
    assert "runtime\\ms-playwright" in content
    assert "Get-NetTCPConnection" in content
    assert "APP_BASE_URL" in content
    assert "pause" in content.lower()
