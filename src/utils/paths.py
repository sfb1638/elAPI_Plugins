import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BASE_DIR / "config"
EXPORT_DIR = BASE_DIR / "json_exports"

RES_IMPORTER_CONFIG = CONFIG_DIR / "res_importer_config.json"
EXP_IMPORTER_CONFIG = CONFIG_DIR / "exp_importer_config.json"
LOGGING_CONFIG = CONFIG_DIR / "logging_config.json"


def log_dir() -> Path:
    """Where log files go.

    In a source checkout that is ``<repo>/logs``. A packaged build unpacks into a
    temporary folder (or sits inside the app bundle), so logs written there are
    lost on exit; they go to the per-user log location instead.
    """
    if not getattr(sys, "frozen", False):
        return BASE_DIR / "logs"
    name = "elAPI_Plugins"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        return base / name / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / name
    state = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(state) / name / "logs"
