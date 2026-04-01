from __future__ import annotations

import csv
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Ensure project root and src/ are first on sys.path so imports resolve correctly
ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_data: Any = None,
        headers: dict | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self.text = text

    def json(self) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


ResponseCallable = Callable[..., "FakeResponse"]


class FakeEndpoint:
    def __init__(
        self,
        get: FakeResponse | ResponseCallable | None = None,
        post: FakeResponse | ResponseCallable | None = None,
        patch: FakeResponse | ResponseCallable | None = None,
        delete: FakeResponse | ResponseCallable | None = None,
    ) -> None:
        self._get = get
        self._post = post
        self._patch = patch
        self._delete = delete

    def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        stub = self._get
        if callable(stub):
            response = stub(*args, **kwargs)
        elif isinstance(stub, FakeResponse):
            response = stub
        else:
            raise AssertionError("FakeEndpoint.get was called without a stub")
        return response

    def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
        stub = self._post
        if callable(stub):
            response = stub(*args, **kwargs)
        elif isinstance(stub, FakeResponse):
            response = stub
        else:
            raise AssertionError("FakeEndpoint.post was called without a stub")
        return response

    def patch(self, *args: Any, **kwargs: Any) -> FakeResponse:
        stub = self._patch
        if callable(stub):
            response = stub(*args, **kwargs)
        elif isinstance(stub, FakeResponse):
            response = stub
        else:
            raise AssertionError("FakeEndpoint.patch was called without a stub")
        return response

    def delete(self, *args: Any, **kwargs: Any) -> FakeResponse:
        stub = self._delete
        if callable(stub):
            response = stub(*args, **kwargs)
        elif isinstance(stub, FakeResponse):
            response = stub
        else:
            return FakeResponse()
        return response


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return path
