#!/usr/bin/env bash
# Build a self-contained Linux binary (+ optional .deb) for the elAPI Plugins GUI.
# Includes elapi/VERSION and elapi/api/_supported_versions so elapi can determine
# its version and supported endpoints at runtime.
#
# The .deb step needs fpm (https://fpm.readthedocs.io):
#   sudo apt install ruby ruby-dev build-essential && sudo gem install --no-document fpm
# If fpm is missing the binary is still built and the script exits cleanly.

set -euo pipefail

# Always run from the project root regardless of where the script is invoked from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Detect OS architecture and map it to the Debian architecture name
OS_ARCH=$(uname -m)
case "$OS_ARCH" in
  x86_64) DEB_ARCH="amd64" ;;
  aarch64|arm64) DEB_ARCH="arm64" ;;
  *) echo "Unsupported architecture: $OS_ARCH" >&2; exit 1 ;;
esac

PKG_NAME="elapi-plugins"   # Debian package names are lowercase
BIN_NAME="elapi-plugins"
ENTRYPOINT="gui/gui.py"
BUILD_ENV=".pkg-build"
DESKTOP_FILE="packaging/${PKG_NAME}.desktop"

# Clean previous build artefacts
rm -rf "$BUILD_ENV" build dist

# Fresh virtualenv for building. PyInstaller bundles whatever is installed in the
# active environment, so this must contain the runtime deps (incl. elapi) *and*
# PyInstaller — hence a dedicated env rather than the dev environment (.build).
python3 -m venv "$BUILD_ENV"
source "$BUILD_ENV/bin/activate"
python -m pip install --upgrade pip wheel setuptools
pip install . pyinstaller

# Read packaging metadata from pyproject.toml so it cannot drift
APP_VERSION=$(python - <<'PY'
import pathlib, tomllib
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)

MAINTAINER=$(python - <<'PY'
import pathlib, tomllib
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
author = data["project"]["authors"][0]
print(f"{author['name']} <{author['email']}>")
PY
)

DESCRIPTION=$(python - <<'PY'
import pathlib, tomllib
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["description"])
PY
)

HOMEPAGE=$(python - <<'PY'
import pathlib, tomllib
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
print(data.get("project", {}).get("urls", {}).get("Homepage", ""))
PY
)

echo "Building ${PKG_NAME} ${APP_VERSION} for ${DEB_ARCH}"

# Find elapi's package root + data files inside the venv
ELAPI_ROOT=$(python - <<'PY'
import importlib.util, pathlib
spec = importlib.util.find_spec('elapi')
if spec is None:
    raise SystemExit("elapi not found in this environment")
print(pathlib.Path(spec.origin).parent.resolve())
PY
)

ELAPI_VERSION_FILE="${ELAPI_ROOT}/VERSION"
ELAPI_SUPPORTED_VERSIONS_DIR="${ELAPI_ROOT}/api/_supported_versions"

if [ ! -f "$ELAPI_VERSION_FILE" ]; then
  echo "ERROR: elapi VERSION file not found: $ELAPI_VERSION_FILE" >&2
  exit 1
fi

if [ ! -d "$ELAPI_SUPPORTED_VERSIONS_DIR" ]; then
  echo "ERROR: elapi supported versions dir not found: $ELAPI_SUPPORTED_VERSIONS_DIR" >&2
  exit 1
fi

# Assemble data files (an array keeps paths with spaces intact).
# NOTE: On Linux, PyInstaller expects --add-data 'SRC:DEST'
DATA_ARGS=(--add-data "gui/templates:templates")
[ -d "gui/static" ] && DATA_ARGS+=(--add-data "gui/static:static")
DATA_ARGS+=(--add-data "${ELAPI_VERSION_FILE}:elapi")
DATA_ARGS+=(--add-data "${ELAPI_SUPPORTED_VERSIONS_DIR}:elapi/api/_supported_versions")
[ -d "config" ] && DATA_ARGS+=(--add-data "config:config")

# Build a single self-contained executable. "--paths ." puts the project root on
# the analysis path so the `src.*` packages imported by gui.py are found.
python -m PyInstaller --clean --onefile \
  --name "$BIN_NAME" \
  --paths . \
  --collect-all pandas \
  "${DATA_ARGS[@]}" \
  "$ENTRYPOINT"

BIN_PATH="dist/${BIN_NAME}"
if [ ! -x "$BIN_PATH" ]; then
  echo "ERROR: expected executable not found: $BIN_PATH" >&2
  exit 1
fi

echo "✅ Binary built: ${BIN_PATH}"

# --- .deb packaging -------------------------------------------------------
if ! command -v fpm >/dev/null 2>&1; then
  echo "ℹ️  fpm not found — skipping .deb creation."
  echo "   Install it with:"
  echo "     sudo apt install ruby ruby-dev build-essential"
  echo "     sudo gem install --no-document fpm"
  exit 0
fi

# Pick an icon: a purpose-made square PNG wins, otherwise fall back to the logo.
# Installed into /usr/share/pixmaps, which (unlike hicolor/<size>) is size-agnostic.
ICON_SRC=""
for candidate in "packaging/${PKG_NAME}.png" "gui/static/logo.png"; do
  if [ -f "$candidate" ]; then
    ICON_SRC="$candidate"
    break
  fi
done

FPM_ARGS=(
  -s dir -t deb
  -n "$PKG_NAME"
  -v "$APP_VERSION"
  -a "$DEB_ARCH"
  --license "AGPL-3.0-or-later"
  --description "$DESCRIPTION"
  --maintainer "$MAINTAINER"
  --deb-priority optional
  --category science
  -p "dist/${PKG_NAME}_${APP_VERSION}_${DEB_ARCH}.deb"
  --force
)
[ -n "$HOMEPAGE" ] && FPM_ARGS+=(--url "$HOMEPAGE")

FPM_INPUTS=("${BIN_PATH}=/usr/bin/${BIN_NAME}")
[ -f "$DESKTOP_FILE" ] &&
  FPM_INPUTS+=("${DESKTOP_FILE}=/usr/share/applications/${PKG_NAME}.desktop")
[ -n "$ICON_SRC" ] &&
  FPM_INPUTS+=("${ICON_SRC}=/usr/share/pixmaps/${PKG_NAME}.png")

fpm "${FPM_ARGS[@]}" "${FPM_INPUTS[@]}"

DEB_PATH="dist/${PKG_NAME}_${APP_VERSION}_${DEB_ARCH}.deb"
echo "📦 Package created: ${DEB_PATH}"
echo "   Install with: sudo apt install ./${DEB_PATH}"
