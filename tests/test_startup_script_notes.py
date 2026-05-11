from pathlib import Path



def test_windows_startup_script_exists_and_mentions_bootstrap_steps() -> None:
    script = Path("start_fly_ticket.bat")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "python" in content.lower()
    assert "playwright install chromium" in content.lower()
    assert ".env.example" in content
    assert "uvicorn" in content.lower()
    assert 'start "Fly Ticket" cmd /k "cd /d "%~dp0" && .venv\\Scripts\\python.exe -m uvicorn' not in content
    assert 'start "Fly Ticket" cmd /k "cd /d "%~dp0%" && .venv\\Scripts\\python.exe -m uvicorn' in content
