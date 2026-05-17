@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title 飞票监控 - 便携版启动器
echo.
echo ==================================================
echo  飞票监控 - 便携版启动器
echo ==================================================
echo.

set "PYTHON_EXE=%CD%\runtime\python\python.exe"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\ms-playwright"

if not exist "%PYTHON_EXE%" (
  echo [错误] 没有找到发布包内置 Python:
  echo %PYTHON_EXE%
  echo 请确认压缩包已经完整解压，不要直接在压缩包里双击运行。
  goto error
)

if not exist "%PLAYWRIGHT_BROWSERS_PATH%" (
  echo [错误] 没有找到发布包内置 Playwright 浏览器运行环境:
  echo %PLAYWRIGHT_BROWSERS_PATH%
  echo 请确认压缩包来自完整的 GitHub Release，并且已经完整解压。
  goto error
)

if not exist ".env" (
  if not exist ".env.example" (
    echo [错误] 缺少 .env，并且没有找到 .env.example。
    goto error
  )
  echo 正在生成本地配置 .env ...
  copy ".env.example" ".env" >nul
  if errorlevel 1 goto error
)

set "PORT="
for /L %%P in (8000,1,8020) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), %%P); try { $listener.Start(); exit 0 } catch { exit 1 } finally { if ($listener) { $listener.Stop() } }"
  if not errorlevel 1 (
    set "PORT=%%P"
    goto port_found
  )
)

echo [ERROR] No available port found from 8000 to 8020.
echo [错误] 8000 到 8020 端口都被占用，无法启动本地服务。
goto error

:port_found
set "APP_BASE_URL=http://127.0.0.1:%PORT%"

echo 正在启动飞票监控: %APP_BASE_URL%
echo 请保持本窗口打开；关闭窗口后监控也会停止。
echo.
start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo [错误] 飞票监控启动失败。
echo 请查看上方提示。常见原因：压缩包未完整解压、运行环境被安全软件拦截、端口被占用。
echo 如果问题仍然存在，可以截图本窗口内容后再反馈。
pause
exit /b 1
