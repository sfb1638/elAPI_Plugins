from __future__ import annotations

import logging

from src.utils.logging_config import _coerce_level, setup_logging


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
