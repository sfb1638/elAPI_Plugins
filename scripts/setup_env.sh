#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

PROJECT_ENV=".build"

uv venv --clear "$PROJECT_ENV"
source "$PROJECT_ENV/bin/activate"
uv sync --active --frozen --all-extras --all-groups
