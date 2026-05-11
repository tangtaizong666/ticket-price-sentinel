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
