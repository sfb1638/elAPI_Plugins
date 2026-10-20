from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.utils.logging_config import (
    SKIPPED_LOG_FILE,
    SKIPPED_LOGGER,
    _coerce_level,
    setup_logging,
)


def test_coerce_level_handles_strings_and_ints() -> None:
    assert _coerce_level("10") == 10
    assert _coerce_level("debug") == "DEBUG"
    assert _coerce_level(20) == 20
    assert _coerce_level(None) is None


def test_setup_logging_runs_idempotently() -> None:
    setup_logging(level="INFO", force=True)
    logger = logging.getLogger("test")
    logger.info("logging initialized")
    # Call again to ensure guard works without raising
    setup_logging(level="INFO", force=False)


def test_log_dir_is_repo_logs_when_not_packaged() -> None:
    from src.utils.paths import BASE_DIR, log_dir

    assert log_dir() == BASE_DIR / "logs"


def test_log_dir_is_per_user_when_packaged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from src.utils import paths

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    assert paths.log_dir() == tmp_path / "elAPI_Plugins" / "logs"
    assert paths.BASE_DIR not in paths.log_dir().parents


@pytest.fixture
def restore_logging() -> Iterator[None]:
    yield
    setup_logging(level="INFO", force=True)  # back to the real log folder


def test_skipped_rows_have_their_own_log_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, restore_logging: None
) -> None:
    from src.utils import logging_config

    monkeypatch.setattr(logging_config, "log_dir", lambda: tmp_path)
    setup_logging(level="INFO", force=True)

    logging.getLogger(SKIPPED_LOGGER).warning("Row 4: something is wrong")
    logging.getLogger("some.other.module").warning("an ordinary warning")
    for handler in logging.getLogger(SKIPPED_LOGGER).handlers:
        handler.flush()
    for handler in logging.getLogger().handlers:
        handler.flush()

    skipped = (tmp_path / SKIPPED_LOG_FILE).read_text(encoding="utf-8")
    assert "Row 4: something is wrong" in skipped
    assert "an ordinary warning" not in skipped  # only skipped rows go there
    assert "Row 4" not in (tmp_path / "app.log").read_text(encoding="utf-8")
    assert logging_config.skipped_log_path() == tmp_path / SKIPPED_LOG_FILE
