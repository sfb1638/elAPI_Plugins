from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BASE_DIR / "config"
EXPORT_DIR = BASE_DIR / "json_exports"

RES_IMPORTER_CONFIG = CONFIG_DIR / "res_importer_config.json"
EXP_IMPORTER_CONFIG = CONFIG_DIR / "exp_importer_config.json"
LOGGING_CONFIG = CONFIG_DIR / "logging_config.json"
