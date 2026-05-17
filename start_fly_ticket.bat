@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title Fly Ticket / 飞票监控 - GitHub 源码启动器
echo.
echo ==================================================
echo  Fly Ticket / 飞票监控 - GitHub 源码启动器
echo ==================================================
echo.

set "PYTHON_VERSION=3.12.8"
set "PYTHON_ZIP_SHA256=8D3F33BE9EB810F23C102F08475AF2854E50484B8E4E06275E937BE61CE3D2FB"
set "GET_PIP_SHA256=66904BCCB878E363DB6236EA900E6935E507DCB887E9F178F6212EDFE7F46A76"
set "RUNTIME_DIR=%CD%\runtime"
set "RUNTIME_PYTHON_DIR=%RUNTIME_DIR%\python"
set "DOWNLOAD_DIR=%RUNTIME_DIR%\downloads"
set "PYTHON_EXE=%RUNTIME_PYTHON_DIR%\python.exe"
set "PYTHON_ZIP=%DOWNLOAD_DIR%\python-%PYTHON_VERSION%-embed-amd64.zip"
set "GET_PIP=%DOWNLOAD_DIR%\get-pip.py"
set "PLAYWRIGHT_BROWSERS_PATH=%RUNTIME_DIR%\ms-playwright"
set "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000"
set "SOURCE_VENV_DIR=%CD%\.venv"
set "SOURCE_VENV_PYTHON=%SOURCE_VENV_DIR%\Scripts\python.exe"

if exist "%PYTHON_EXE%" goto python_ready

set "BOOTSTRAP_PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 set "BOOTSTRAP_PYTHON_CMD=py -3"

if not defined BOOTSTRAP_PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "BOOTSTRAP_PYTHON_CMD=python"
)

if defined BOOTSTRAP_PYTHON_CMD (
  %BOOTSTRAP_PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 goto create_venv
)

goto bootstrap_runtime_python

:create_venv
if exist ".venv" if not exist "%SOURCE_VENV_PYTHON%" (
  echo 检测到已有 .venv 不是 Windows 虚拟环境，改用 .venv-windows ...
  set "SOURCE_VENV_DIR=%CD%\.venv-windows"
  set "SOURCE_VENV_PYTHON=%CD%\.venv-windows\Scripts\python.exe"
)
if not exist "%SOURCE_VENV_PYTHON%" (
  echo 正在创建虚拟环境 %SOURCE_VENV_DIR% ...
  %BOOTSTRAP_PYTHON_CMD% -m venv "%SOURCE_VENV_DIR%"
  if errorlevel 1 goto bootstrap_runtime_python
)
set "PYTHON_EXE=%SOURCE_VENV_PYTHON%"
goto python_ready

:bootstrap_runtime_python
echo 没有找到可用的 Python 3.10 或更高版本，正在准备内置 Python 运行环境。
echo 首次运行需要联网下载 Python 和依赖，之后会复用 runtime 目录。

if not exist "%DOWNLOAD_DIR%" mkdir "%DOWNLOAD_DIR%"
if errorlevel 1 goto error
if not exist "%RUNTIME_PYTHON_DIR%" mkdir "%RUNTIME_PYTHON_DIR%"
if errorlevel 1 goto error

echo 正在下载 Python %PYTHON_VERSION% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip' -OutFile '%PYTHON_ZIP%'; $hash = (Get-FileHash -LiteralPath '%PYTHON_ZIP%' -Algorithm SHA256).Hash.ToUpperInvariant(); if ($hash -ne '%PYTHON_ZIP_SHA256%') { throw ('Python zip SHA256 mismatch: ' + $hash) }"
if errorlevel 1 goto error

echo 正在解压内置 Python ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%RUNTIME_PYTHON_DIR%' -Force; $pth = Get-ChildItem -LiteralPath '%RUNTIME_PYTHON_DIR%' -Filter 'python*._pth' | Select-Object -First 1; if (-not $pth) { throw 'Unable to find embedded Python ._pth file.' }; $content = Get-Content -LiteralPath $pth.FullName; $content = $content | ForEach-Object { if ($_ -eq '#import site') { 'import site' } else { $_ } }; Set-Content -LiteralPath $pth.FullName -Value $content -Encoding ASCII"
if errorlevel 1 goto error

echo 正在下载 pip 安装器 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GET_PIP%'; $hash = (Get-FileHash -LiteralPath '%GET_PIP%' -Algorithm SHA256).Hash.ToUpperInvariant(); if ($hash -ne '%GET_PIP_SHA256%') { throw ('get-pip.py SHA256 mismatch: ' + $hash) }"
if errorlevel 1 goto error

echo 正在安装 pip ...
"%PYTHON_EXE%" "%GET_PIP%"
if errorlevel 1 goto error

:python_ready
if not exist "%PYTHON_EXE%" (
  echo [错误] 没有找到可用 Python:
  echo %PYTHON_EXE%
  goto error
)

if not exist ".env" (
  echo 正在从 .env.example 生成本地配置 .env ...
  copy ".env.example" ".env" >nul
  if errorlevel 1 goto error
)

echo 正在安装/更新运行依赖，请稍等...
call "%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo 正在安装/检查 Playwright Chromium 浏览器运行环境...
call "%PYTHON_EXE%" -m playwright install chromium
if errorlevel 1 goto error

set "PORT="
for /L %%P in (8000,1,8020) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), %%P); try { $listener.Start(); exit 0 } catch { exit 1 } finally { if ($listener) { $listener.Stop() } }"
  if not errorlevel 1 (
    set "PORT=%%P"
    goto port_found
  )
)

echo [错误] 8000 到 8020 端口都被占用，无法启动本地服务。
goto error

:port_found
set "APP_BASE_URL=http://127.0.0.1:%PORT%"

echo.
echo 正在启动飞票监控: %APP_BASE_URL%
echo 请保持本窗口打开；关闭窗口后监控也会停止。
echo.
start "" cmd /c "timeout /t 2 /nobreak >nul && start "" "%APP_BASE_URL%""
call "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo [错误] 飞票监控启动失败。
echo 请查看上方提示。常见原因：网络下载失败、安全软件拦截、依赖安装失败或端口被占用。
echo 如果问题仍然存在，可以截图本窗口内容后再反馈。
pause
exit /b 1
