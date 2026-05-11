param(
    [string]$Version = "dev",
    [string]$PythonVersion = "3.12.8",
    [string]$DistRoot = "dist"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$distRootPath = Join-Path $repoRoot $DistRoot
$packageName = "FlyTicket-Windows"
$packageRoot = Join-Path $distRootPath $packageName
$runtimeRoot = Join-Path $packageRoot "runtime"
$pythonRoot = Join-Path $runtimeRoot "python"
$browserRoot = Join-Path $runtimeRoot "ms-playwright"
$dataRoot = Join-Path $packageRoot "data"
$downloadsRoot = Join-Path $distRootPath "_downloads"
$archivePath = Join-Path $distRootPath "$packageName-$Version.zip"

$excludedNames = @(
    ".env",
    ".venv",
    "data",
    ".pytest_cache",
    "__pycache__",
    "requirements-dev.txt",
    "playwright-profile",
    "app.db",
    "last_live_search"
)

$excludedState = @(
    ".env",
    "data",
    "playwright-profile",
    "app.db",
    "last_live_search"
)

function Remove-PathIfExists {
    param([string]$Path)

    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Copy-RequiredItem {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path $Source)) {
        throw "Required release input was not found: $Source"
    }

    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Copy-OptionalItem {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path $Source) {
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    }
}

Remove-PathIfExists -Path $packageRoot
Remove-PathIfExists -Path $downloadsRoot
Remove-PathIfExists -Path $archivePath

New-Item -ItemType Directory -Force -Path $pythonRoot | Out-Null
New-Item -ItemType Directory -Force -Path $browserRoot | Out-Null
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
New-Item -ItemType Directory -Force -Path $downloadsRoot | Out-Null

$pythonZip = Join-Path $downloadsRoot "python-$PythonVersion-embed-amd64.zip"
$pythonZipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$getPip = Join-Path $downloadsRoot "get-pip.py"

Invoke-WebRequest -Uri $pythonZipUrl -OutFile $pythonZip
Expand-Archive -Path $pythonZip -DestinationPath $pythonRoot -Force

$pthFile = Get-ChildItem -Path $pythonRoot -Filter "python*._pth" | Select-Object -First 1
if (-not $pthFile) {
    throw "Unable to find embedded Python ._pth file."
}

$pthContent = Get-Content -LiteralPath $pthFile.FullName
$pthContent = $pthContent | ForEach-Object {
    if ($_ -eq "#import site") {
        "import site"
    }
    else {
        $_
    }
}
Set-Content -LiteralPath $pthFile.FullName -Value $pthContent -Encoding ASCII

Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
& (Join-Path $pythonRoot "python.exe") $getPip
& (Join-Path $pythonRoot "python.exe") -m pip install --no-warn-script-location -r (Join-Path $repoRoot "requirements.txt")

$env:PLAYWRIGHT_BROWSERS_PATH = $browserRoot
& (Join-Path $pythonRoot "python.exe") -m playwright install chromium

Copy-RequiredItem -Source (Join-Path $repoRoot "app") -Destination (Join-Path $packageRoot "app")
Copy-RequiredItem -Source (Join-Path $repoRoot ".env.example") -Destination (Join-Path $packageRoot ".env.example")
Copy-OptionalItem -Source (Join-Path $repoRoot "README_使用说明.txt") -Destination (Join-Path $packageRoot "README_使用说明.txt")
Copy-RequiredItem -Source (Join-Path $repoRoot "scripts/launch_portable.bat") -Destination (Join-Path $packageRoot "启动机票监控.bat")

foreach ($name in $excludedNames) {
    $path = Join-Path $packageRoot $name
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

foreach ($stateName in $excludedState) {
    if ($stateName -eq "data") {
        continue
    }

    $statePath = Join-Path $packageRoot $stateName
    if (Test-Path $statePath) {
        Remove-Item -LiteralPath $statePath -Recurse -Force
    }
}

Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $archivePath -Force
Write-Host "Created $archivePath"
