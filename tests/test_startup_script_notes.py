from pathlib import Path


def _count_bare_lf(path: Path) -> int:
    content = path.read_bytes()
    return sum(
        1
        for index, byte in enumerate(content)
        if byte == 0x0A and (index == 0 or content[index - 1] != 0x0D)
    )


def test_windows_batch_launchers_use_crlf_line_endings() -> None:
    assert _count_bare_lf(Path("start_fly_ticket.bat")) == 0
    assert _count_bare_lf(Path("scripts/launch_portable.bat")) == 0


def test_source_startup_script_keeps_errors_visible() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert "pause" in content.lower()
    assert "Fly Ticket" in content


def test_source_startup_script_can_bootstrap_runtime_without_system_python() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert 'set "RUNTIME_PYTHON_DIR=%RUNTIME_DIR%\\python"' in content
    assert 'set "PYTHON_EXE=%RUNTIME_PYTHON_DIR%\\python.exe"' in content
    assert "python-%PYTHON_VERSION%-embed-amd64.zip" in content
    assert "https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip" in content
    assert "https://bootstrap.pypa.io/get-pip.py" in content
    assert "Get-FileHash" in content
    assert "8D3F33BE9EB810F23C102F08475AF2854E50484B8E4E06275E937BE61CE3D2FB" in content
    assert "66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76" in content


def test_source_startup_script_installs_runtime_requirements_only() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert "requirements.txt" in content
    assert "requirements-dev.txt" not in content
    assert "playwright install chromium" in content.lower()
    assert 'set "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000"' in content


def test_source_startup_script_preserves_non_windows_venv_directories() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert 'set "SOURCE_VENV_DIR=%CD%\\.venv"' in content
    assert 'set "SOURCE_VENV_PYTHON=%SOURCE_VENV_DIR%\\Scripts\\python.exe"' in content
    assert 'set "SOURCE_VENV_DIR=%CD%\\.venv-windows"' in content
    assert 'set "SOURCE_VENV_PYTHON=%CD%\\.venv-windows\\Scripts\\python.exe"' in content
    assert "检测到已有 .venv 不是 Windows 虚拟环境" in content


def test_source_startup_script_uses_batch_safe_powershell_quoting() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert '\\"' not in content
    assert "throw ('Python zip SHA256 mismatch: ' + $hash)" in content
    assert "throw ('get-pip.py SHA256 mismatch: ' + $hash)" in content


def test_source_startup_script_copies_env_before_installing_browser() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    env_copy_index = content.index('copy ".env.example" ".env"')
    playwright_install_index = content.lower().index("playwright install chromium")

    assert env_copy_index < playwright_install_index


def test_source_startup_script_validates_supported_python_version() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert "sys.version_info >= (3, 10)" in content
    assert "Python 3.10" in content
    assert "-c \"import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)\"" in content


def test_source_startup_script_finds_available_local_port() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")

    assert "TcpListener" in content
    assert "[System.Net.IPAddress]::Parse('127.0.0.1')" in content
    assert "for /L %%P in (8000,1,8020)" in content
    assert 'set "APP_BASE_URL=http://127.0.0.1:%PORT%"' in content
    assert 'start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""' in content
    assert 'call "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%' in content


def test_source_startup_script_delays_browser_open_until_server_starts() -> None:
    content = Path("start_fly_ticket.bat").read_text(encoding="utf-8")
    lower_content = content.lower()
    lines = [line.strip().lower() for line in content.splitlines()]

    assert "timeout /t" in lower_content
    assert 'start "" cmd /c' in lower_content
    assert 'start "" http://127.0.0.1:8000' not in lines
    assert "http://127.0.0.1:8000" not in content


def test_portable_launcher_uses_bundled_python_only() -> None:
    script = Path("scripts/launch_portable.bat")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "runtime\\python\\python.exe" in content
    assert "where python" not in content.lower()
    assert "where py" not in content.lower()
    assert "pip install" not in content.lower()
    assert "playwright install" not in content.lower()


def test_portable_launcher_uses_its_own_directory_as_package_root() -> None:
    content = Path("scripts/launch_portable.bat").read_text(encoding="utf-8")

    assert 'cd /d "%~dp0"' in content
    assert 'cd /d "%~dp0\\.."' not in content


def test_portable_launcher_sets_browser_path_and_finds_port() -> None:
    content = Path("scripts/launch_portable.bat").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSERS_PATH" in content
    assert "runtime\\ms-playwright" in content
    assert "TcpListener" in content
    assert ".Start()" in content
    assert 'set "APP_BASE_URL=http://127.0.0.1:%PORT%"' in content
    assert 'start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""' in content
    assert content.index('set "APP_BASE_URL=http://127.0.0.1:%PORT%"') < content.index(
        'start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""'
    )


def test_portable_launcher_port_probe_does_not_ignore_wildcard_listeners() -> None:
    content = Path("scripts/launch_portable.bat").read_text(encoding="utf-8")

    assert "TcpListener" in content
    assert "[System.Net.IPAddress]::Parse('127.0.0.1')" in content
    assert "-LocalAddress 127.0.0.1" not in content
    assert "Get-NetTCPConnection" not in content


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
