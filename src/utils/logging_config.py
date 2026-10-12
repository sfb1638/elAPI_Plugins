from __future__ import annotations

import logging
import logging.config
import os

from src.utils.common import load_config
from src.utils.paths import LOGGING_CONFIG, log_dir


def _coerce_level(level: str | int | None) -> str | int | None:
    """Coerce input to a logging level or None."""
    if level is None:
        return None
    if isinstance(level, int):
        return level
    level_str = str(level).strip().upper()
    if not level_str:
        return None
    if level_str.isdigit():
        return int(level_str)
    return level_str


def setup_logging(level: str | int | None = None, force: bool = False) -> None:
    """Load logging config from JSON once, honoring LOG_LEVEL env/override."""
    if getattr(setup_logging, "_configured", False) and not force:
        return

    logging_config = load_config(LOGGING_CONFIG)

    env_level = os.getenv("LOG_LEVEL")
    desired_level = _coerce_level(level or env_level)

    if desired_level is not None:
        logging_config.setdefault("root", {})["level"] = desired_level
    elif str(logging_config.get("root", {}).get("level", "")).lower() == "level":
        logging_config.setdefault("root", {})["level"] = "INFO"

    for handler in logging_config.get("handlers", {}).values():
        filename = handler.get("filename")
        if filename:
            log_path = log_dir() / filename
            log_path.parent.mkdir(parents=True, exist_ok=True)

            handler["filename"] = str(log_path)

    logging.config.dictConfig(logging_config)
    setup_logging._configured = True  # type: ignore[attr-defined]
