import json
import math
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, TypeVar

try:
    import httpx
except ImportError:  # pragma: no cover - available via elapi at runtime
    httpx = None

import pandas as pd
from bs4 import BeautifulSoup
from requests.exceptions import (  # type: ignore[import-untyped]
    ConnectTimeout,
    ReadTimeout,
)


def strip_html(html_str: str) -> str:
    """Return plain text from HTML."""
    soup = BeautifulSoup(html_str or "", "html.parser")

    paragraphs = soup.find_all("p")
    if paragraphs:
        texts = [p.get_text(separator=" ", strip=True) for p in paragraphs]
        return "\n\n".join(texts)

    return soup.get_text(separator=" ", strip=True)


def canonicalize(name: str) -> str:
    return name.lower().replace(" ", "").replace("-", "_")


def ensure_series(row: Any) -> pd.Series | None:
    """Return a Series built from the input, or ``None`` when conversion fails."""
    if isinstance(row, pd.Series):
        return row
    if hasattr(row, "_asdict"):
        try:
            return pd.Series(row._asdict())
        except Exception:
            return None
    return None


def load_config(config_path: str | Path) -> dict:
    try:
        with open(config_path, encoding="utf-8") as f:
            config_file: dict = json.load(f)
            return config_file

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Config file not found. Tried: {config_path}. "
            "Set RES_IMPORTER_CONFIG to override, or ensure "
            "config/res_importer_config.json exists at repo root."
        ) from None

    except json.JSONDecodeError as exc:
        raise ValueError(f"Error decoding JSON from {config_path}: {exc}") from exc


T = TypeVar("T")
Timeouts: tuple[type[BaseException], ...] = (ReadTimeout, ConnectTimeout)
if httpx is not None:
    Timeouts += (httpx.ReadTimeout, httpx.ConnectTimeout)


def paged_fetch(
    get_page: Callable[[int, int], Sequence[T]],
    *,
    start_offset: int = 0,
    page_size: int = 30,
    max_retries: int = 3,
    min_limit: int = 5,
    backoff_s: Callable[[int], float] = lambda attempt: 1.5 * attempt,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> Iterator[T]:
    """Iterate pages with retries, adaptive limits, and optional progress callback."""
    offset = start_offset

    while True:
        attempt = 0
        current_limit = page_size

        while True:
            try:
                page = list(get_page(current_limit, offset))
                break
            except Timeouts:
                if attempt >= max_retries:
                    page = []
                    break
                attempt += 1
                time.sleep(backoff_s(attempt))
                current_limit = max(min_limit, math.ceil(current_limit / 2))

        if not page:
            # Exhausted retries: skip this window and advance
            if attempt >= max_retries:
                if on_progress:
                    on_progress(0, offset, current_limit)
                offset += current_limit
                continue
            break

        if on_progress:
            on_progress(len(page), offset, current_limit)

        yield from page

        if len(page) < current_limit:
            break

        offset += current_limit
