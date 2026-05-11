@echo off
setlocal
cd /d %~dp0

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 was not found. Install Python and try again.
    exit /b 1
  )
  set "PYTHON_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 exit /b 1
)

call ".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 exit /b 1

call ".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 exit /b 1

if not exist ".env" (
  copy ".env.example" ".env" >nul
  if errorlevel 1 exit /b 1
)

start "Fly Ticket" cmd /k "cd /d "%~dp0%" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "" http://127.0.0.1:8000
