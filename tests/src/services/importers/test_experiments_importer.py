from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.services.importers import experiments_importer as exp_module
from tests.conftest import FakeEndpoint, FakeResponse, write_csv


def test_create_new(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_post(**kwargs: Any) -> FakeResponse:
        return FakeResponse(headers={"Location": "http://x/experiments/123"})

    monkeypatch.setattr(
        exp_module, "get_fixed", lambda name: FakeEndpoint(post=fake_post)
    )

    csv_path = write_csv(tmp_path / "exp.csv", ["title"], [["t"]])
    importer = exp_module.ExperimentsImporter(csv_path)
    assert importer.create_new("t", ["a"]) == "123"


def test_patch_existing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, dict[str, Any]] = {"data": {}}

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if not isinstance(data, dict):
            data = {}
        captured["data"] = data
        return FakeResponse()

    monkeypatch.setattr(
        exp_module, "get_fixed", lambda name: FakeEndpoint(patch=fake_patch)
    )

    csv_path = write_csv(
        tmp_path / "exp.csv",
        ["title", "body", "tags"],
        [["t", "b", "a,b"]],
    )
    importer = exp_module.ExperimentsImporter(csv_path)

    called = {"extra": False}

    def fake_update(*args: Any, **kwargs: Any) -> None:
        called["extra"] = True

    monkeypatch.setattr(importer, "update_extra_fields_from_row", fake_update)

    row = importer.basic_df.iloc[0]
    status = importer.patch_existing(1, row, category="45")

    assert status == 200
    assert captured["data"]["title"] == "t"
    assert "tags" in captured["data"]
    assert captured["data"]["body"] == "b"
    assert captured["data"]["category"] == "45"
    assert called["extra"]


def test_experiment_import_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(exp_module, "get_fixed", lambda name: FakeEndpoint())

    csv_path = write_csv(
        tmp_path / "exp.csv",
        ["id", "title"],
        [["", "t1"], ["2", "t2"]],
    )
    importer = exp_module.ExperimentsImporter(csv_path)

    calls = {"created": 0, "patched": 0}

    def fake_create(*args: Any, **kwargs: Any) -> str:
        calls["created"] += 1
        return "1"

    def fake_patch(*args: Any, **kwargs: Any) -> int:
        calls["patched"] += 1
        return 200

    monkeypatch.setattr(importer, "create_new", fake_create)
    monkeypatch.setattr(importer, "patch_existing", fake_patch)

    importer.experiment_import()

    assert calls["created"] == 1
    assert calls["patched"] == 2
