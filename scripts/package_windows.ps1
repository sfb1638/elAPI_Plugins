# Build a self-contained Windows .exe for ELAPI GUI.
# Includes elapi/VERSION and elapi/api/_supported_versions so elapi can determine
# its version and supported endpoints at runtime.
# Windows PowerShell equivalent of scripts/package_mac.sh (macOS)

param(
    [string]$Architecture = "x64"  # x64 or x86
)

$ErrorActionPreference = "Stop"

# Always run from the project root regardless of where the script is invoked from
Set-Location (Split-Path -Parent $PSScriptRoot)

# Validate architecture
if ($Architecture -notmatch "^(x64|x86)$") {
    Write-Error "Unsupported architecture: $Architecture. Use x64 or x86"
    exit 1
}

$APP_BASE = "elAPI_Plugins"
$APP_NAME = "${APP_BASE}_${Architecture}"
$ENTRYPOINT = "gui/gui.py"
$BUILD_ENV = ".pkg-build"

Write-Host "Building $APP_NAME for Windows ($Architecture)" -ForegroundColor Cyan

# Clean previous build artifacts
if (Test-Path $BUILD_ENV) { Remove-Item -Path $BUILD_ENV -Recurse -Force }
if (Test-Path "build") { Remove-Item -Path "build" -Recurse -Force }
if (Test-Path "dist") { Remove-Item -Path "dist" -Recurse -Force }

# Locate a usable interpreter. A bare "python" on Windows is often the Microsoft
# Store alias, which is not a real interpreter, so prefer the py launcher and
# resolve the actual executable before relying on it.
Write-Host "Locating Python interpreter..." -ForegroundColor Yellow
$PythonExe = $null

if (Get-Command py -ErrorAction SilentlyContinue) {
    $resolved = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved) { $PythonExe = "$resolved".Trim() }
}
if (-not $PythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $resolved = & python -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved) { $PythonExe = "$resolved".Trim() }
}
if (-not $PythonExe) {
    Write-Error @"
No usable Python interpreter found.
Install Python 3.11+ from https://www.python.org/downloads/windows/ and tick
"Add python.exe to PATH" during setup. If 'python' opens the Microsoft Store,
disable the alias under Settings > Apps > Advanced app settings >
App execution aliases.
"@
    exit 1
}
Write-Host "Using Python: $PythonExe" -ForegroundColor Green

# Create fresh virtual environment for building
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
& $PythonExe -m venv $BUILD_ENV
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create the virtual environment in $BUILD_ENV"
    exit 1
}

# Call the environment's interpreter directly rather than activating it, so the
# build cannot silently fall back to a different Python.
$VenvPython = Join-Path $BUILD_ENV "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment is missing an interpreter: $VenvPython"
    exit 1
}

# Upgrade pip and install build tools
Write-Host "Installing build dependencies..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip wheel setuptools
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to upgrade pip/wheel/setuptools"; exit 1 }
& $VenvPython -m pip install . pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to install the project and PyInstaller"; exit 1 }

# Verify Python architecture matches requested architecture
Write-Host "Verifying Python architecture..." -ForegroundColor Yellow
$archScript = @'
import struct
print('x64' if struct.calcsize('P') == 8 else 'x86')
'@

$PY_ARCH = & $VenvPython -c $archScript

if ($PY_ARCH -ne $Architecture) {
    Write-Error "Python arch ($PY_ARCH) != requested arch ($Architecture). Make sure you're using the correct Python version."
    exit 1
}

Write-Host "Python architecture verified: $PY_ARCH" -ForegroundColor Green

# Find elapi's package root + data files
Write-Host "Locating elapi package and data files..." -ForegroundColor Yellow

$pythonScript = @'
import importlib.util, pathlib
spec = importlib.util.find_spec('elapi')
if spec is None:
    raise SystemExit('elapi not found in this environment')
root = pathlib.Path(spec.origin).parent
print(str((root / 'VERSION').resolve()))
'@

$ELAPI_VERSION_FILE = & $VenvPython -c $pythonScript

if (-not (Test-Path $ELAPI_VERSION_FILE)) {
    Write-Error "ERROR: elapi VERSION file not found: $ELAPI_VERSION_FILE"
    exit 1
}

$pythonScript2 = @'
import importlib.util, pathlib
spec = importlib.util.find_spec('elapi')
if spec is None:
    raise SystemExit('elapi not found in this environment')
root = pathlib.Path(spec.origin).parent
d = root / 'api' / '_supported_versions'
print(str(d.resolve()))
'@

$ELAPI_SUPPORTED_VERSIONS_DIR = & $VenvPython -c $pythonScript2

if (-not (Test-Path $ELAPI_SUPPORTED_VERSIONS_DIR)) {
    Write-Error "ERROR: elapi supported versions dir not found: $ELAPI_SUPPORTED_VERSIONS_DIR"
    exit 1
}

Write-Host "Found elapi VERSION: $ELAPI_VERSION_FILE" -ForegroundColor Green
Write-Host "Found supported versions: $ELAPI_SUPPORTED_VERSIONS_DIR" -ForegroundColor Green

# Assemble data files for PyInstaller
# NOTE: On Windows, PyInstaller expects --add-data 'SRC;DEST'
Write-Host "Assembling data files..." -ForegroundColor Yellow

$DATA_ARGS = @()
$DATA_ARGS += "--add-data", "gui/templates;templates"

if (Test-Path "gui/static") {
    $DATA_ARGS += "--add-data", "gui/static;static"
}

$DATA_ARGS += "--add-data", "$ELAPI_VERSION_FILE;elapi"
$DATA_ARGS += "--add-data", "$ELAPI_SUPPORTED_VERSIONS_DIR;elapi/api/_supported_versions"

if (Test-Path "config") {
    $DATA_ARGS += "--add-data", "config;config"
}

# Optional icon (the app icon lives under gui/assets)
$ICON_PATH = "gui/assets/app.ico"
$ICON_ARG = @()
if (Test-Path $ICON_PATH) {
    $ICON_ARG = "--icon", $ICON_PATH
    Write-Host "Using icon: $ICON_PATH" -ForegroundColor Green
} else {
    Write-Warning "Icon not found at $ICON_PATH; building without a custom icon."
}

# Build the .exe with PyInstaller
Write-Host "Building executable with PyInstaller..." -ForegroundColor Cyan

$pyinstaller_cmd = @(
    "-m", "PyInstaller",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "$APP_NAME",
    "--collect-all", "pandas"
) + $ICON_ARG + $DATA_ARGS + @($ENTRYPOINT)

& $VenvPython $pyinstaller_cmd

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
    exit 1
}

Write-Host "Executable built: dist/$APP_NAME.exe" -ForegroundColor Green

# Sanity check: --onefile bundles everything (incl. elapi data) into a single .exe,
# so there is no extracted folder to inspect at build time; just confirm the exe exists.
$EXE_PATH = "dist/$APP_NAME.exe"
if (-not (Test-Path $EXE_PATH)) {
    Write-Error "Expected executable not found: $EXE_PATH"
    exit 1
}
Write-Host "Build verification passed: $EXE_PATH" -ForegroundColor Green

# Test the executable
Write-Host "Testing executable..." -ForegroundColor Yellow
Write-Host "To test manually, run: .\dist\$APP_NAME.exe" -ForegroundColor Cyan

# Optional: Create installer with Inno Setup
Write-Host "Next step: Create Windows installer (optional)" -ForegroundColor Yellow
Write-Host "Install Inno Setup from: https://jrsoftware.org/isdl.php" -ForegroundColor Cyan
Write-Host "Then compile the installer, e.g.:" -ForegroundColor Cyan
Write-Host "  ISCC /DArch=$Architecture packaging\installer.iss" -ForegroundColor Cyan

Write-Host ""
Write-Host "Build complete!" -ForegroundColor Green
Write-Host "Executable: dist/$APP_NAME.exe" -ForegroundColor Green
