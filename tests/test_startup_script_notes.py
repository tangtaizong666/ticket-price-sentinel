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
