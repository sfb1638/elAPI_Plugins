#!/usr/bin/env bash
# Build a self-contained macOS .app + DMG for ELAPI GUI.
# Includes elapi/VERSION and elapi/api/_supported_versions so elapi can determine
# its version and supported endpoints at runtime.

set -euo pipefail

# Detect OS architecture (x86_64 or arm64)
OS_ARCH=$(uname -m)
case "$OS_ARCH" in
  x86_64|arm64) : ;;
  *) echo "Unsupported architecture: $OS_ARCH" >&2; exit 1 ;;
esac

APP_BASE="elAPI_Plugins"
APP_NAME="${APP_BASE}_${OS_ARCH}"
ENTRYPOINT="gui/gui.py"
BUILD_ENV=".pkg-build"

# Clean previous build artefacts
rm -rf "$BUILD_ENV" build dist

# Fresh virtualenv for building
python3 -m venv "$BUILD_ENV"
source "$BUILD_ENV/bin/activate"
python -m pip install --upgrade pip wheel setuptools
pip install . pyinstaller

# Sanity check: ensure Python we’re using matches OS arch (avoid Rosetta pitfalls)
PY_ARCH=$(python - <<'PY'
import platform
print(platform.machine())
PY
)

if [ "$PY_ARCH" != "$OS_ARCH" ]; then
  echo "Python arch ($PY_ARCH) != OS arch ($OS_ARCH)."
  echo "On Apple Silicon, ensure you use native arm64 Python (e.g., /opt/homebrew/bin/python3),"
  echo "or remove Rosetta from the build shell. Aborting."
  exit 1
fi

# Find elapi’s package root + data files inside the venv
ELAPI_VERSION_FILE=$(python - <<'PY'
import importlib.util, pathlib
spec = importlib.util.find_spec('elapi')
if spec is None:
    raise SystemExit("elapi not found in this environment")
root = pathlib.Path(spec.origin).parent
print((root / 'VERSION').resolve())
PY
)

ELAPI_SUPPORTED_VERSIONS_DIR=$(python - <<'PY'
import importlib.util, pathlib
spec = importlib.util.find_spec('elapi')
if spec is None:
    raise SystemExit("elapi not found in this environment")
root = pathlib.Path(spec.origin).parent
d = root / "api" / "_supported_versions"
print(d.resolve())
PY
)

if [ ! -f "$ELAPI_VERSION_FILE" ]; then
  echo "ERROR: elapi VERSION file not found: $ELAPI_VERSION_FILE" >&2
  exit 1
fi

if [ ! -d "$ELAPI_SUPPORTED_VERSIONS_DIR" ]; then
  echo "ERROR: elapi supported versions dir not found: $ELAPI_SUPPORTED_VERSIONS_DIR" >&2
  exit 1
fi

# Assemble data files
# NOTE: On macOS, PyInstaller expects --add-data 'SRC:DEST'
DATA_ARGS="--add-data gui/templates:templates"
[ -d "gui/static" ] && DATA_ARGS="$DATA_ARGS --add-data gui/static:static"
DATA_ARGS="$DATA_ARGS --add-data $ELAPI_VERSION_FILE:elapi"
DATA_ARGS="$DATA_ARGS --add-data ${ELAPI_SUPPORTED_VERSIONS_DIR}:elapi/api/_supported_versions"
[ -d "config" ] && DATA_ARGS="$DATA_ARGS --add-data config:config"

# Optional icon
ICON_ARG=""
[ -f app.icns ] && ICON_ARG="--icon app.icns"

# Build the .app
python -m PyInstaller --clean --windowed \
  --name "$APP_NAME" \
  $ICON_ARG \
  $DATA_ARGS \
  "$ENTRYPOINT"

echo "✅ App built: dist/${APP_NAME}.app"

# Optional signing to reduce Gatekeeper prompts
if command -v codesign >/dev/null 2>&1; then
  codesign --deep --force --sign - "dist/${APP_NAME}.app" || true
fi

# Sanity check: ensure supported versions JSONs are inside the bundle
if [ ! -d "dist/${APP_NAME}.app/Contents/Frameworks/elapi/api/_supported_versions" ]; then
  echo "ERROR: Bundle missing elapi/api/_supported_versions inside .app" >&2
  echo "Expected: dist/${APP_NAME}.app/Contents/Frameworks/elapi/api/_supported_versions" >&2
  exit 1
fi

echo "🔎 Bundled supported versions:"
ls -la "dist/${APP_NAME}.app/Contents/Frameworks/elapi/api/_supported_versions" || true

cd dist
DMG_NAME="${APP_NAME}-macOS.dmg"
hdiutil create -volname "$APP_BASE" \
  -srcfolder "${APP_NAME}.app" \
  -ov -format UDZO "$DMG_NAME"

echo "📦 DMG created: $(pwd)/$DMG_NAME"
