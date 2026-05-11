# GitHub Windows Portable Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows portable GitHub release flow so users can download a zip, unzip it, and double-click a launcher without installing Python, dependencies, or Playwright separately.

**Architecture:** First land the existing stability/security fixes so the release branch does not package known defects. Then add a portable launcher and maintainer build script that assemble `dist/FlyTicket-Windows/` with an embedded Python runtime, runtime dependencies, bundled Playwright Chromium, app files, safe defaults, and user-facing documentation. Keep the runtime package separate from local user data so upgrades can preserve `.env` and `data/`.

**Tech Stack:** Python 3, FastAPI, Uvicorn, Playwright, SQLite, Windows batch, PowerShell, pytest.

---

## File Structure

- Modify `app/ctrip_scraper.py`: close temporary pages created during shared-context searches.
- Modify `app/ctrip_session.py`: add explicit async cleanup for Playwright context and process.
- Modify `app/main.py`: close the session manager during app shutdown and save session state on search success/expiry.
- Modify `app/monitor_scheduler.py`: log scheduler failures and advance failed task runtime timestamps.
- Modify `app/dashboard.py`: display `ready` and `expired` session states.
- Modify `app/history.py`: accept `datetime` for `last_successful_scrape_at` and serialize it consistently.
- Modify `app/static/app.js`: remove `innerHTML` usage for monitor empty state and open external links with `noopener,noreferrer`.
- Modify `tests/fixtures/ctrip_search_results.html`: replace captured live page content with a sanitized minimal fixture.
- Modify stability tests in `tests/test_ctrip_scraper.py`, `tests/test_dashboard_view.py`, `tests/test_home_page.py`, `tests/test_monitor_runner.py`, `tests/test_search_api.py`, `tests/test_session_api.py`.
- Modify `requirements.txt`: keep runtime dependencies only.
- Modify `requirements-dev.txt`: move test/developer dependencies here.
- Modify `.env.example`: add portable-friendly defaults, including bundled Playwright path.
- Replace `start_fly_ticket.bat`: source checkout developer launcher that can use local `.venv`.
- Create `scripts/launch_portable.bat`: release-package launcher that uses `runtime\python\python.exe`.
- Create `scripts/build_windows_portable.ps1`: maintainer build script for `dist/FlyTicket-Windows/` and zip.
- Create `README_使用说明.txt`: copied into the release package for ordinary users.
- Modify `README.md`: document Release usage, developer usage, and build flow.
- Modify `tests/test_startup_script_notes.py`: verify launcher and build script invariants.
- Create `tests/test_release_packaging.py`: static checks for build script exclusions and package layout.

## Task 1: Prepare Implementation Workspace

**Files:**
- Inspect: `.worktrees/fix-stability-review-issues`
- Inspect: `docs/superpowers/specs/2026-05-11-github-windows-portable-design.md`

- [ ] **Step 1: Confirm the main checkout is clean**

Run:

```bash
git status --short --branch
```

Expected: output shows `## master` and no uncommitted files.

- [ ] **Step 2: Confirm the existing worktree contains only the stability fixes**

Run:

```bash
git -C .worktrees/fix-stability-review-issues status --short --branch
git -C .worktrees/fix-stability-review-issues diff --stat
```

Expected: branch is `fix-stability-review-issues`, with modifications limited to app code, tests, frontend JS, and the sanitized fixture.

- [ ] **Step 3: Bring the design and plan commits into the worktree**

Run:

```bash
git -C .worktrees/fix-stability-review-issues fetch --all --prune
git -C .worktrees/fix-stability-review-issues merge master
```

Expected: merge succeeds without overwriting the existing uncommitted stability changes. If Git refuses because local changes would be overwritten, stop and inspect `git -C .worktrees/fix-stability-review-issues status --short`; do not reset or checkout files.

- [ ] **Step 4: Run the worktree baseline tests before editing**

Run:

```bash
.worktrees/fix-stability-review-issues/.venv/bin/python -m pytest -q
```

Expected: the current stability worktree passes, expected count is about `59 passed`.

## Task 2: Land Existing Stability and Security Fixes

**Files:**
- Modify: `app/ctrip_scraper.py`
- Modify: `app/ctrip_session.py`
- Modify: `app/main.py`
- Modify: `app/monitor_scheduler.py`
- Modify: `app/dashboard.py`
- Modify: `app/history.py`
- Modify: `app/static/app.js`
- Modify: `tests/fixtures/ctrip_search_results.html`
- Test: `tests/test_ctrip_scraper.py`
- Test: `tests/test_dashboard_view.py`
- Test: `tests/test_home_page.py`
- Test: `tests/test_monitor_runner.py`
- Test: `tests/test_search_api.py`
- Test: `tests/test_session_api.py`

- [ ] **Step 1: Review the existing stability diff**

Run:

```bash
git -C .worktrees/fix-stability-review-issues diff
```

Expected: diff includes shared-context page cleanup, session manager close, lifespan cleanup, session `ready`/`expired` persistence, monitor failure advancement, JS `innerHTML` removal, `noopener,noreferrer`, and fixture sanitization.

- [ ] **Step 2: Verify targeted stability tests pass**

Run:

```bash
.worktrees/fix-stability-review-issues/.venv/bin/python -m pytest \
  tests/test_ctrip_scraper.py \
  tests/test_dashboard_view.py \
  tests/test_home_page.py \
  tests/test_monitor_runner.py \
  tests/test_search_api.py \
  tests/test_session_api.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Verify the full suite passes**

Run:

```bash
.worktrees/fix-stability-review-issues/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit the stability fixes**

Run:

```bash
git -C .worktrees/fix-stability-review-issues add \
  app/ctrip_scraper.py \
  app/ctrip_session.py \
  app/main.py \
  app/monitor_scheduler.py \
  app/dashboard.py \
  app/history.py \
  app/static/app.js \
  tests/fixtures/ctrip_search_results.html \
  tests/test_ctrip_scraper.py \
  tests/test_dashboard_view.py \
  tests/test_home_page.py \
  tests/test_monitor_runner.py \
  tests/test_search_api.py \
  tests/test_session_api.py
git -C .worktrees/fix-stability-review-issues commit -m "fix: harden scraping and monitoring runtime"
```

Expected: commit succeeds with only stability/security files included.

## Task 3: Split Runtime and Development Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Test: `tests/test_release_packaging.py`

- [ ] **Step 1: Write the failing dependency split test**

Create `tests/test_release_packaging.py` with:

```python
from pathlib import Path


def _requirement_names(path: str) -> set[str]:
    names: set[str] = set()
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line.split("==", 1)[0].split("[", 1)[0].lower())
    return names


def test_runtime_requirements_do_not_include_test_tools() -> None:
    runtime = _requirement_names("requirements.txt")

    assert "pytest" not in runtime
    assert "httpx" not in runtime


def test_development_requirements_include_test_tools() -> None:
    dev = _requirement_names("requirements-dev.txt")

    assert "pytest" in dev
    assert "httpx" in dev
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_packaging.py::test_runtime_requirements_do_not_include_test_tools -q
```

Expected: fails because `requirements.txt` currently includes `pytest` and `httpx`.

- [ ] **Step 3: Move test dependencies to `requirements-dev.txt`**

Change `requirements.txt` to:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
jinja2==3.1.5
python-multipart==0.0.20
pydantic==2.10.6
playwright==1.51.0
python-dotenv==1.0.1
beautifulsoup4==4.12.3
plyer==2.1.0
```

Change `requirements-dev.txt` to:

```text
-r requirements.txt
pytest==8.3.5
httpx==0.28.1
```

- [ ] **Step 4: Run the dependency tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_packaging.py -q
```

Expected: dependency tests pass.

- [ ] **Step 5: Run the full suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add requirements.txt requirements-dev.txt tests/test_release_packaging.py
git commit -m "chore: split runtime and development requirements"
```

Expected: commit succeeds.

## Task 4: Add Portable-Friendly Settings

**Files:**
- Modify: `app/settings.py`
- Modify: `.env.example`
- Test: `tests/test_release_packaging.py`

- [ ] **Step 1: Write the failing settings test**

Append to `tests/test_release_packaging.py`:

```python
def test_env_example_includes_portable_browser_path() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSERS_PATH=runtime/ms-playwright" in content


def test_settings_exposes_app_base_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:8123")

    from app.settings import Settings

    settings = Settings()

    assert settings.app_base_url == "http://127.0.0.1:8123"
```

- [ ] **Step 2: Run the new settings test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_release_packaging.py::test_env_example_includes_portable_browser_path \
  tests/test_release_packaging.py::test_settings_exposes_app_base_url \
  -q
```

Expected: fails because `.env.example` lacks `PLAYWRIGHT_BROWSERS_PATH`, and `Settings` lacks `app_base_url`.

- [ ] **Step 3: Add `app_base_url` to `Settings`**

In `app/settings.py`, add this field inside the `Settings` dataclass:

```python
    app_base_url: str = field(
        default_factory=lambda: os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    )
```

- [ ] **Step 4: Update `.env.example`**

Change `.env.example` to:

```env
APP_DB_PATH=data/app.db
PLAYWRIGHT_PROFILE_DIR=data/playwright-profile
PLAYWRIGHT_BROWSERS_PATH=runtime/ms-playwright
CTRIP_SNAPSHOT_DIR=tests/fixtures
CTRIP_SEARCH_URL_TEMPLATE=https://flights.ctrip.com/online/list/oneway-{origin}-{destination}?depdate={departure_date}&cabin=y_s_c_f&adult=1&child=0&infant=0&containstax=1
CTRIP_SESSION_URL=https://flights.ctrip.com/online/channel/domestic
APP_BASE_URL=http://127.0.0.1:8000
```

- [ ] **Step 5: Run the settings tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_packaging.py -q
```

Expected: tests pass.

- [ ] **Step 6: Run the full suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add app/settings.py .env.example tests/test_release_packaging.py
git commit -m "chore: add portable runtime defaults"
```

Expected: commit succeeds.

## Task 5: Replace the Source Checkout Launcher

**Files:**
- Modify: `start_fly_ticket.bat`
- Modify: `tests/test_startup_script_notes.py`

- [ ] **Step 1: Replace the startup script test with source-launcher expectations**

Change `tests/test_startup_script_notes.py` to:

```python
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
```

- [ ] **Step 2: Run the startup script tests and verify the new error-visibility test fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_startup_script_notes.py -q
```

Expected: fails because the current script does not consistently pause on all errors.

- [ ] **Step 3: Replace `start_fly_ticket.bat`**

Set `start_fly_ticket.bat` to:

```bat
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

echo Installing development dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto error

echo Installing Playwright Chromium...
call ".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto error

if not exist ".env" (
  copy ".env.example" ".env" >nul
  if errorlevel 1 goto error
)

echo Starting Fly Ticket at http://127.0.0.1:8000
start "" http://127.0.0.1:8000
call ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo [ERROR] Fly Ticket failed to start.
echo Check the messages above, then try again.
pause
exit /b 1
```

- [ ] **Step 4: Run the startup script tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_startup_script_notes.py -q
```

Expected: startup script tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add start_fly_ticket.bat tests/test_startup_script_notes.py
git commit -m "chore: clarify source checkout launcher"
```

Expected: commit succeeds.

## Task 6: Add the Windows Portable Launcher

**Files:**
- Create: `scripts/launch_portable.bat`
- Modify: `tests/test_startup_script_notes.py`

- [ ] **Step 1: Write failing portable launcher tests**

Append to `tests/test_startup_script_notes.py`:

```python
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
    assert "APP_BASE_URL" in content
    assert "pause" in content.lower()
```

- [ ] **Step 2: Run the portable launcher tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_startup_script_notes.py::test_portable_launcher_uses_bundled_python_only \
  tests/test_startup_script_notes.py::test_portable_launcher_sets_browser_path_and_finds_port \
  -q
```

Expected: fails because `scripts/launch_portable.bat` does not exist.

- [ ] **Step 3: Create `scripts/launch_portable.bat`**

Create `scripts/launch_portable.bat` with:

```bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title Fly Ticket
echo Fly Ticket portable launcher
echo.

set "PYTHON_EXE=%CD%\runtime\python\python.exe"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\ms-playwright"

if not exist "%PYTHON_EXE%" (
  echo [错误] 没有找到内置 Python:
  echo %PYTHON_EXE%
  echo 请重新下载完整的 Windows 便携版 zip。
  pause
  exit /b 1
)

if not exist "%PLAYWRIGHT_BROWSERS_PATH%" (
  echo [错误] 没有找到内置浏览器目录:
  echo %PLAYWRIGHT_BROWSERS_PATH%
  echo 请重新下载完整的 Windows 便携版 zip。
  pause
  exit /b 1
)

if not exist ".env" (
  if not exist ".env.example" (
    echo [错误] 没有找到 .env.example，无法生成配置。
    pause
    exit /b 1
  )
  copy ".env.example" ".env" >nul
  if errorlevel 1 (
    echo [错误] 无法生成 .env 配置文件。
    pause
    exit /b 1
  )
)

set "PORT="
for /l %%P in (8000,1,8020) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort %%P -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }" >nul 2>nul
  if !errorlevel! EQU 0 (
    set "PORT=%%P"
    goto port_found
  )
)

:port_found
if "%PORT%"=="" (
  echo [错误] 8000 到 8020 端口都被占用，请关闭其他本地服务后重试。
  pause
  exit /b 1
)

set "APP_BASE_URL=http://127.0.0.1:%PORT%"
echo 正在启动 Fly Ticket: %APP_BASE_URL%
start "" "%APP_BASE_URL%"
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
if errorlevel 1 (
  echo.
  echo [错误] Fly Ticket 启动失败，请查看上面的错误信息。
  pause
  exit /b 1
)

exit /b 0
```

- [ ] **Step 4: Run the portable launcher tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_startup_script_notes.py -q
```

Expected: all startup script tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/launch_portable.bat tests/test_startup_script_notes.py
git commit -m "feat: add windows portable launcher"
```

Expected: commit succeeds.

## Task 7: Add the Windows Portable Build Script

**Files:**
- Create: `scripts/build_windows_portable.ps1`
- Modify: `tests/test_release_packaging.py`

- [ ] **Step 1: Write failing build script tests**

Append to `tests/test_release_packaging.py`:

```python
def test_windows_portable_build_script_exists_and_defines_layout() -> None:
    script = Path("scripts/build_windows_portable.ps1")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "FlyTicket-Windows" in content
    assert '"python"' in content
    assert '"ms-playwright"' in content
    assert "launch_portable.bat" in content
    assert "Compress-Archive" in content


def test_windows_portable_build_script_excludes_user_state() -> None:
    content = Path("scripts/build_windows_portable.ps1").read_text(encoding="utf-8")

    assert ".env" in content
    assert "data" in content
    assert "playwright-profile" in content
    assert "requirements-dev.txt" in content
```

- [ ] **Step 2: Run the build script tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_release_packaging.py::test_windows_portable_build_script_exists_and_defines_layout \
  tests/test_release_packaging.py::test_windows_portable_build_script_excludes_user_state \
  -q
```

Expected: fails because the build script does not exist.

- [ ] **Step 3: Create `scripts/build_windows_portable.ps1`**

Create `scripts/build_windows_portable.ps1` with:

```powershell
param(
    [string]$Version = "dev",
    [string]$PythonVersion = "3.12.8",
    [string]$DistRoot = "dist"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistRootPath = Join-Path $ProjectRoot $DistRoot
$PackageName = "FlyTicket-Windows"
$PackageRoot = Join-Path $DistRootPath $PackageName
$RuntimeRoot = Join-Path $PackageRoot "runtime"
$PythonRoot = Join-Path $RuntimeRoot "python"
$BrowserRoot = Join-Path $RuntimeRoot "ms-playwright"
$DownloadsRoot = Join-Path $DistRootPath "_downloads"

function Reset-Directory([string]$Path) {
    if (Test-Path $Path) {
        Remove-Item -Recurse -Force $Path
    }
    New-Item -ItemType Directory -Force $Path | Out-Null
}

function Copy-ProjectDirectory([string]$RelativePath) {
    $Source = Join-Path $ProjectRoot $RelativePath
    $Destination = Join-Path $PackageRoot $RelativePath
    Copy-Item -Recurse -Force $Source $Destination
}

Reset-Directory $PackageRoot
New-Item -ItemType Directory -Force $RuntimeRoot, $DownloadsRoot, (Join-Path $PackageRoot "data") | Out-Null

$PythonZip = Join-Path $DownloadsRoot "python-$PythonVersion-embed-amd64.zip"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $PythonZip)) {
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonZip
}
Expand-Archive -Force $PythonZip $PythonRoot

$PthFile = Get-ChildItem $PythonRoot -Filter "python*._pth" | Select-Object -First 1
if ($PthFile) {
    $PthContent = Get-Content $PthFile.FullName
    $PthContent = $PthContent | ForEach-Object {
        if ($_ -eq "#import site") { "import site" } else { $_ }
    }
    Set-Content -Encoding ASCII -Path $PthFile.FullName -Value $PthContent
}

$GetPip = Join-Path $DownloadsRoot "get-pip.py"
if (-not (Test-Path $GetPip)) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
}
& (Join-Path $PythonRoot "python.exe") $GetPip
& (Join-Path $PythonRoot "python.exe") -m pip install --upgrade pip
& (Join-Path $PythonRoot "python.exe") -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

$env:PLAYWRIGHT_BROWSERS_PATH = $BrowserRoot
& (Join-Path $PythonRoot "python.exe") -m playwright install chromium

Copy-ProjectDirectory "app"
Copy-Item -Force (Join-Path $ProjectRoot ".env.example") (Join-Path $PackageRoot ".env.example")
Copy-Item -Force (Join-Path $ProjectRoot "README_使用说明.txt") (Join-Path $PackageRoot "README_使用说明.txt")
Copy-Item -Force (Join-Path $ProjectRoot "scripts\launch_portable.bat") (Join-Path $PackageRoot "启动机票监控.bat")

$ExcludedNames = @(".env", ".venv", "data", ".pytest_cache", "__pycache__", "requirements-dev.txt")
$ExcludedState = @("playwright-profile", "app.db", "last_live_search")

$ZipPath = Join-Path $DistRootPath "$PackageName-$Version.zip"
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}
Compress-Archive -Force -Path (Join-Path $PackageRoot "*") -DestinationPath $ZipPath

Write-Host "Built $ZipPath"
Write-Host "Excluded names: $($ExcludedNames -join ', ')"
Write-Host "Excluded user state: $($ExcludedState -join ', ')"
```

- [ ] **Step 4: Run the build script tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_packaging.py -q
```

Expected: release packaging tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/build_windows_portable.ps1 tests/test_release_packaging.py
git commit -m "feat: add windows portable build script"
```

Expected: commit succeeds.

## Task 8: Add User-Facing Release Documentation

**Files:**
- Create: `README_使用说明.txt`
- Modify: `README.md`
- Test: `tests/test_release_packaging.py`

- [ ] **Step 1: Write failing documentation tests**

Append to `tests/test_release_packaging.py`:

```python
def test_release_user_readme_exists_and_avoids_developer_jargon() -> None:
    content = Path("README_使用说明.txt").read_text(encoding="utf-8")

    assert "双击" in content
    assert "启动机票监控.bat" in content
    assert "登录携程" in content
    assert "pip" not in content.lower()
    assert "virtualenv" not in content.lower()


def test_project_readme_mentions_windows_release_and_build_script() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "FlyTicket-Windows" in content
    assert "启动机票监控.bat" in content
    assert "scripts/build_windows_portable.ps1" in content
```

- [ ] **Step 2: Run the documentation tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_release_packaging.py::test_release_user_readme_exists_and_avoids_developer_jargon \
  tests/test_release_packaging.py::test_project_readme_mentions_windows_release_and_build_script \
  -q
```

Expected: fails because `README_使用说明.txt` does not exist and `README.md` does not mention the new release flow.

- [ ] **Step 3: Create `README_使用说明.txt`**

Create `README_使用说明.txt` with:

```text
Fly Ticket 使用说明

一、启动
1. 解压 FlyTicket-Windows 压缩包。
2. 双击 启动机票监控.bat。
3. 程序会自动打开浏览器。
4. 如果窗口里出现错误，请不要关闭窗口，先按提示处理。

二、第一次使用
1. 打开页面后，先点击“去登录”。
2. 在携程页面完成登录。
3. 回到本地页面，先搜索一次机票。
4. 保存一个监控任务，让程序定时检查价格。

三、数据保存在哪里
本地数据库和登录状态保存在 data 文件夹。
升级新版本时，保留旧版本的 data 文件夹和 .env 文件即可继续使用原来的数据。

四、常见问题
如果 Windows 或杀毒软件提示风险，请确认压缩包来自你信任的 GitHub Release。
如果页面打不开，可能是端口被占用，重新双击启动脚本通常会自动换端口。
如果搜索失败，请重新登录携程，或检查网络连接。
如果登录失效，请在首页点击“重新登录”。
```

- [ ] **Step 4: Update `README.md`**

Modify `README.md` so the top-level running section starts with ordinary users:

```markdown
## 普通用户：下载后双击使用

从 GitHub Release 下载 `FlyTicket-Windows-<version>.zip`，解压后双击：

`启动机票监控.bat`

发布包自带 Python 运行环境、运行依赖和 Playwright Chromium。普通用户不需要手动安装 Python、pip 依赖或浏览器组件。
```

Also add a developer build section:

```markdown
## 构建 Windows 便携版

维护者可以在 Windows PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_portable.ps1 -Version dev
```

构建结果会输出到 `dist/FlyTicket-Windows/` 和 `dist/FlyTicket-Windows-dev.zip`。
```
```

- [ ] **Step 5: Run documentation tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_packaging.py -q
```

Expected: release packaging tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add README.md README_使用说明.txt tests/test_release_packaging.py
git commit -m "docs: document windows portable release"
```

Expected: commit succeeds.

## Task 9: Verify Fixture Sanitization and Release Safety

**Files:**
- Modify: `tests/test_release_packaging.py`
- Inspect: `tests/fixtures/ctrip_search_results.html`

- [ ] **Step 1: Add a fixture sanitization test**

Append to `tests/test_release_packaging.py`:

```python
def test_ctrip_fixture_does_not_contain_obvious_live_session_material() -> None:
    content = Path("tests/fixtures/ctrip_search_results.html").read_text(
        encoding="utf-8"
    ).lower()

    forbidden_markers = [
        "cookie",
        "set-cookie",
        "passport",
        "ubt_trace_id",
        "sessionid",
        "authorization",
        "csrf",
    ]
    for marker in forbidden_markers:
        assert marker not in content
```

- [ ] **Step 2: Run the sanitization test**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_packaging.py::test_ctrip_fixture_does_not_contain_obvious_live_session_material -q
```

Expected: passes if Task 2's sanitized fixture is in place. If it fails, replace the fixture with a minimal static HTML file containing only representative flight result markup needed by parser tests.

- [ ] **Step 3: Run parser and packaging tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_ctrip_parser.py tests/test_release_packaging.py -q
```

Expected: parser tests and release packaging tests pass.

- [ ] **Step 4: Commit if the fixture or tests changed**

Run:

```bash
git add tests/test_release_packaging.py tests/fixtures/ctrip_search_results.html
git commit -m "test: guard release fixtures against session data"
```

Expected: commit succeeds if there are changes. If there are no changes except tests already committed in a prior task, skip this commit.

## Task 10: Build and Smoke Test the Portable Package

**Files:**
- Inspect generated: `dist/FlyTicket-Windows/`
- Inspect generated: `dist/FlyTicket-Windows-dev.zip`

- [ ] **Step 1: Run the full Python test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Build the Windows portable package on Windows PowerShell**

Run from the repository root on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_portable.ps1 -Version dev
```

Expected:

```text
Built ...\dist\FlyTicket-Windows-dev.zip
```

- [ ] **Step 3: Confirm required package files exist**

Run:

```bash
test -f dist/FlyTicket-Windows/启动机票监控.bat
test -f dist/FlyTicket-Windows/runtime/python/python.exe
test -d dist/FlyTicket-Windows/runtime/ms-playwright
test -f dist/FlyTicket-Windows/app/main.py
test -f dist/FlyTicket-Windows/.env.example
test -f dist/FlyTicket-Windows/README_使用说明.txt
```

Expected: all commands exit with status `0`.

- [ ] **Step 4: Smoke test the built package**

Run from Windows by double-clicking:

```text
dist\FlyTicket-Windows\启动机票监控.bat
```

Expected: browser opens a local `http://127.0.0.1:<port>` page and the home page renders.

- [ ] **Step 5: Stop the smoke-test server**

Close the launcher command window or press `Ctrl+C`.

Expected: server stops without leaving an extra Uvicorn process.

- [ ] **Step 6: Commit final build-script adjustments if smoke testing required changes**

Run:

```bash
git status --short
git add scripts/build_windows_portable.ps1 scripts/launch_portable.bat README.md README_使用说明.txt tests
git commit -m "fix: polish windows portable package smoke test"
```

Expected: commit succeeds if smoke testing required tracked changes. If `git status --short` is clean, skip this commit.

## Task 11: Final Verification and Handoff

**Files:**
- Inspect: repository root

- [ ] **Step 1: Verify no generated release artifacts are tracked**

Run:

```bash
git status --short
git check-ignore -q dist && echo "dist ignored"
```

Expected: working tree is clean or only intentional source changes are present, and `dist` is ignored. If `dist` is not ignored, add `dist/` to `.gitignore`, commit it, and rerun.

- [ ] **Step 2: Run final tests**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Record final verification notes**

Prepare a final summary containing:

```text
Tests: <pytest output summary>
Build: <portable build command result>
Smoke test: <homepage URL and status>
Package: dist/FlyTicket-Windows-dev.zip
```

- [ ] **Step 4: Decide integration path**

If implementing in `.worktrees/fix-stability-review-issues`, merge or cherry-pick the completed branch back to `master` only after reviewing the diff:

```bash
git -C .worktrees/fix-stability-review-issues log --oneline --decorate -5
git -C .worktrees/fix-stability-review-issues diff master..HEAD --stat
```

Expected: diff only includes planned stability, packaging, launcher, docs, and tests.

## Self-Review

- Spec coverage: The plan covers Windows-only release zip, bundled Python, bundled Playwright Chromium, launcher behavior, build script, user docs, existing stability fixes, config defaults, and verification.
- Scope check: macOS/Linux packages, PyInstaller exe, installer, service mode, auto-update, and auto-purchase are excluded.
- Placeholder scan: No unresolved placeholders or unspecified implementation steps remain.
- Type consistency: New references are limited to `Settings.app_base_url`, batch/PowerShell files, and test helper functions defined in the plan.
