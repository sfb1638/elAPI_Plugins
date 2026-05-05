from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import httpx
import pytest
from requests.exceptions import (  # type: ignore[import-untyped]
    ConnectTimeout,
    ReadTimeout,
)

from src.utils.common import (
    canonicalize,
    ensure_series,
    load_config,
    paged_fetch,
    strip_html,
)


def test_strip_html_extracts_paragraphs() -> None:
    html = "<p>First</p><p>Second&nbsp;line</p>"
    assert strip_html(html) == "First\n\nSecond\xa0line"


def test_canonicalize_removes_spaces_and_dashes() -> None:
    assert canonicalize("My Field-Name") == "myfield_name"


def test_paged_fetch_retries_and_reduces_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []

    def fake_sleep(seconds: float) -> None:
        # avoid slowing down the test
        return None

    def get_page(limit: int, offset: int) -> list[int]:
        calls.append((limit, offset))
        if len(calls) == 1:
            raise ReadTimeout()
        if len(calls) == 2:
            raise ConnectTimeout()
        return [offset + i for i in range(3)]

    monkeypatch.setattr(time, "sleep", fake_sleep)

    items = list(
        paged_fetch(
            get_page,
            start_offset=0,
            page_size=6,
            max_retries=3,
            min_limit=2,
        )
    )

    assert items == [0, 1, 2, 2, 3, 4]
    # Expect initial call, retry with reduced limit after each timeout
    assert calls[:3] == [(6, 0), (3, 0), (2, 0)]


def test_paged_fetch_retries_on_httpx_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def fake_sleep(seconds: float) -> None:
        return None

    def get_page(limit: int, offset: int) -> list[int]:
        calls.append((limit, offset))
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow response")
        if len(calls) == 2:
            raise httpx.ConnectTimeout("slow connect")
        return [offset + i for i in range(2)]

    monkeypatch.setattr(time, "sleep", fake_sleep)

    items = list(
        paged_fetch(
            get_page,
            start_offset=0,
            page_size=8,
            max_retries=3,
            min_limit=2,
        )
    )

    assert items == [0, 1, 2, 3]
    assert calls[:4] == [(8, 0), (4, 0), (2, 0), (8, 2)]


def test_paged_fetch_stops_when_page_short() -> None:
    pages: Iterator[list[int]] = iter([[1, 2], [3]])

    def get_page(limit: int, offset: int) -> list[int]:
        _limit: int = limit  # keep for type checking
        try:
            return next(pages)
        except StopIteration:
            return []

    items = list(paged_fetch(get_page, page_size=2))
    assert items == [1, 2, 3]


def test_ensure_series_accepts_namedtuple() -> None:
    class Row(NamedTuple):
        a: int
        b: str

    row = Row(1, "x")
    series = ensure_series(row)
    assert series is not None
    assert series["a"] == 1
    assert series["b"] == "x"


def test_load_config_reads_json(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"a": 1}', encoding="utf-8")
    loaded = load_config(config_path)
    assert loaded["a"] == 1


def test_load_config_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.json"))
