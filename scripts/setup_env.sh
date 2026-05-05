#!/usr/bin/env bash

set -euo pipefail

PROJECT_ENV=".build"

uv venv --clear "$PROJECT_ENV"
source "$PROJECT_ENV/bin/activate"
uv sync --active --frozen --all-extras --all-groups
