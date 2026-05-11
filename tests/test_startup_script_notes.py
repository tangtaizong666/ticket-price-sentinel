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
    assert 'set "APP_BASE_URL=http://127.0.0.1:%PORT%"' in content
    assert 'start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""' in content
    assert content.index('set "APP_BASE_URL=http://127.0.0.1:%PORT%"') < content.index(
        'start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""'
    )


def test_portable_launcher_port_probe_does_not_ignore_wildcard_listeners() -> None:
    content = Path("scripts/launch_portable.bat").read_text(encoding="utf-8")

    assert "Get-NetTCPConnection" in content
    assert "-LocalPort %%P" in content
    assert "-LocalAddress 127.0.0.1" not in content


def test_portable_launcher_routes_error_branches_to_pausing_error_label() -> None:
    content = Path("scripts/launch_portable.bat").read_text(encoding="utf-8")
    lower_content = content.lower()

    assert "\n:error\n" in content
    error_block = lower_content.split("\n:error\n", 1)[1]
    assert "pause" in error_block
    assert "exit /b 1" in error_block

    missing_python_index = content.index('if not exist "%PYTHON_EXE%" (')
    missing_browser_index = content.index('if not exist "%PLAYWRIGHT_BROWSERS_PATH%" (')
    missing_env_example_index = content.index('if not exist ".env.example" (')
    env_copy_failure_index = content.index('copy ".env.example" ".env" >nul')
    no_port_index = content.index("echo [ERROR] No available port found from 8000 to 8020.")
    server_failure_index = content.index(
        '"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%'
    )
    error_label_index = content.index("\n:error\n")

    for branch_index in (
        missing_python_index,
        missing_browser_index,
        missing_env_example_index,
        env_copy_failure_index,
        no_port_index,
        server_failure_index,
    ):
        assert branch_index < content.index("goto error", branch_index) < error_label_index
