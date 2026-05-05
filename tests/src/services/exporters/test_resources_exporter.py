from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.services.exporters import resources_exporter as res_module
from tests.conftest import FakeEndpoint, FakeResponse


def test_xlsx_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_get(**kwargs: object) -> FakeResponse:
        return FakeResponse(json_data=[{"id": 1, "metadata": "{}"}])

    monkeypatch.setattr(res_module, "get_fixed", lambda name: FakeEndpoint(get=fake_get))

    exporter = res_module.ResourcesExporter(category_id=1)

    def fake_to_excel(self: object, path: str | Path, index: bool = False) -> None:
        Path(path).write_text("x", encoding="utf-8")

    monkeypatch.setattr(pd.DataFrame, "to_excel", fake_to_excel, raising=True)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    out = exporter.xlsx_export("res.xlsx")
    assert out.exists()
