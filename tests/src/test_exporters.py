from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.services.exporters.experiments_exporter import ExperimentsExporter
from src.services.exporters.resources_exporter import ResourcesExporter
from tests.conftest import FakeEndpoint, FakeResponse


class _SimpleEndpoint(FakeEndpoint):
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        if self._pages:
            return FakeResponse(json_data=self._pages.pop(0))
        return FakeResponse(json_data={"data": []})


def test_resources_exporter_process_data_extracts_extra_and_strips_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, Any]] = [
        {
            "data": [
                {
                    "id": 1,
                    "body": "<p>Hello</p>",
                    "metadata": {"extra_fields": {"Extra": {"value": "X"}}},
                }
            ]
        },
        {"data": []},
    ]
    endpoint = _SimpleEndpoint(pages)

    monkeypatch.setattr(
        "src.services.exporters.resources_exporter.get_fixed", lambda name: endpoint
    )

    exporter = ResourcesExporter(category_id=1)
    df = exporter.process_data()

    extra_col = "metadata.extra_fields.Extra.value"
    assert extra_col in df.columns
    assert df.at[0, extra_col] == "X"
    assert df.at[0, "body"] == "Hello"


def test_resources_exporter_fetch_data_returns_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, Any]] = [{"data": [{"id": 1}]}, {"data": []}]
    endpoint = _SimpleEndpoint(pages)

    monkeypatch.setattr(
        "src.services.exporters.resources_exporter.get_fixed", lambda name: endpoint
    )

    exporter = ResourcesExporter(category_id=1)
    df = exporter.fetch_data(page_size=10)

    assert not df.empty


def test_resources_exporter_xlsx_export_writes_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exporter = ResourcesExporter.__new__(ResourcesExporter)
    exporter._category_id = 1
    exporter._endpoint = None

    dummy_df = pd.DataFrame([{"body": "hi"}])
    monkeypatch.setattr(ResourcesExporter, "process_data", lambda self: dummy_df)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    out = ResourcesExporter.xlsx_export(exporter, export_file="out.xlsx")
    assert out.exists()
    assert out.suffix == ".xlsx"


def test_experiments_exporter_process_data(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = ExperimentsExporter.__new__(ExperimentsExporter)
    exporter._endpoint = None

    df_in = pd.DataFrame(
        [
            {
                "metadata": {"extra_fields": {"Field": {"value": "V"}}},
                "body": "<p>Text</p>",
            }
        ]
    )
    monkeypatch.setattr(ExperimentsExporter, "fetch_data", lambda self: df_in)

    df_out = ExperimentsExporter.process_data(exporter)
    assert df_out.at[0, "Field"] == "V"
    assert df_out.at[0, "body"] == "Text"


def test_experiments_exporter_xlsx_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exporter = ExperimentsExporter.__new__(ExperimentsExporter)
    exporter._endpoint = None
    dummy_df = pd.DataFrame([{"col": 1}])
    monkeypatch.setattr(ExperimentsExporter, "process_data", lambda self: dummy_df)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    out = ExperimentsExporter.xlsx_export(exporter, export_file=None)
    assert out.exists()
    assert out.suffix == ".xlsx"


def test_experiments_exporter_fetch_data_uses_paged_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    class DummyEndpoint(FakeEndpoint):
        def get(self, **kwargs: Any) -> FakeResponse:
            calls.append(kwargs["query"]["offset"])
            data = {"data": []} if len(calls) > 1 else {"data": [{"id": 1}]}
            return FakeResponse(json_data=data)

    monkeypatch.setattr(
        "src.services.exporters.experiments_exporter.get_fixed",
        lambda name: DummyEndpoint(),
    )

    exporter = ExperimentsExporter()
    df = exporter.fetch_data(page_size=1)

    assert list(df["id"]) == [1]
    assert calls == [0, 1]
