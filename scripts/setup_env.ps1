param()

$ErrorActionPreference = "Stop"

$ProjectEnv = ".build"

uv venv --clear $ProjectEnv
& ".\$ProjectEnv\Scripts\Activate.ps1"
uv sync --active --frozen --all-extras --all-groups
