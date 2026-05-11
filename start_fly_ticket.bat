@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Fly Ticket - Development Launcher
echo Fly Ticket development launcher
echo.

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python 3 was not found.
    echo Install Python 3, then run this script again.
    pause
    exit /b 1
  )
  set "PYTHON_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto error
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  if errorlevel 1 goto error
)

echo Installing development dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto error

set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\ms-playwright"
echo Installing Playwright Chromium...
call ".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto error

echo Starting Fly Ticket at http://127.0.0.1:8000
start "" cmd /c "timeout /t 2 /nobreak >nul && start "" http://127.0.0.1:8000"
call ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo [ERROR] Fly Ticket failed to start.
echo Check the messages above, then try again.
pause
exit /b 1
