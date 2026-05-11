@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

title Fly Ticket - Portable Launcher
echo Fly Ticket portable launcher
echo.

set "PYTHON_EXE=%CD%\runtime\python\python.exe"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\ms-playwright"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Bundled Python was not found:
  echo %PYTHON_EXE%
  goto error
)

if not exist "%PLAYWRIGHT_BROWSERS_PATH%" (
  echo [ERROR] Bundled Playwright browsers were not found:
  echo %PLAYWRIGHT_BROWSERS_PATH%
  goto error
)

if not exist ".env" (
  if not exist ".env.example" (
    echo [ERROR] .env is missing and .env.example was not found.
    goto error
  )
  copy ".env.example" ".env" >nul
  if errorlevel 1 goto error
)

set "PORT="
for /L %%P in (8000,1,8020) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort %%P -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
  if not errorlevel 1 (
    set "PORT=%%P"
    goto port_found
  )
)

echo [ERROR] No available port found from 8000 to 8020.
goto error

:port_found
set "APP_BASE_URL=http://127.0.0.1:%PORT%"

echo Starting Fly Ticket at %APP_BASE_URL%
start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo [ERROR] Fly Ticket failed to start.
echo Check the messages above, then try again.
pause
exit /b 1
