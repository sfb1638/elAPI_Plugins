from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.services.importers import experiments_importer as exp_module
from tests.conftest import FakeEndpoint, FakeResponse, write_csv


def test_create_new_with_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_post(**kwargs: Any) -> FakeResponse:
        return FakeResponse(headers={"Location": "http://x/experiments/123"})

    def fake_patch(**kwargs: Any) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(post=fake_post, patch=fake_patch),
    )

    files_dir = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "a.txt").write_text("x", encoding="utf-8")

    csv_path = write_csv(
        tmp_path / "exp.csv",
        ["title", "attachments"],
        [["t", str(files_dir)]],
    )
    importer = exp_module.ExperimentsImporter(csv_path)

    called = {"attach": 0, "single": 0, "extra": 0}

    def fake_attach(*args: Any, **kwargs: Any) -> None:
        called["attach"] += 1

    def fake_single(*args: Any, **kwargs: Any) -> None:
        called["single"] += 1

    def fake_extra(*args: Any, **kwargs: Any) -> None:
        called["extra"] += 1

    monkeypatch.setattr(importer, "attach_files", fake_attach)
    monkeypatch.setattr(importer, "attach_single_file", fake_single)
    monkeypatch.setattr(importer, "post_extra_fields_from_row", fake_extra)

    experiment_id = importer.create_new(importer.basic_df.iloc[0])

    assert experiment_id == "123"
    assert called["attach"] == 1
    assert called["single"] == 0
    assert called["extra"] == 1


def test_patch_existing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, dict[str, Any]] = {"data": {}}

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": {"extra_fields": {}}})

    def fake_post(**kwargs: Any) -> FakeResponse:
        return FakeResponse()

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if not isinstance(data, dict):
            data = {}
        captured["data"] = data
        return FakeResponse()

    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, post=fake_post, patch=fake_patch),
    )

    csv_path = write_csv(
        tmp_path / "exp.csv",
        ["title", "body", "tags"],
        [["t", "b", "a,b"]],
    )
    importer = exp_module.ExperimentsImporter(csv_path)

    called = {"extra": False}

    def fake_extra(*args: Any, **kwargs: Any) -> None:
        called["extra"] = True

    monkeypatch.setattr(importer, "post_extra_fields_from_row", fake_extra)

    row = importer.basic_df.iloc[0]
    status = importer.patch_existing("1", row, category="45")

    assert status == 200
    assert captured["data"]["title"] == "t"
    assert captured["data"]["body"] == "b"
    assert captured["data"]["category"] == "45"
    assert called["extra"]


def test_create_all_from_csv_new(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(),
    )

    csv_path = write_csv(
        tmp_path / "exp.csv",
        ["title"],
        [["t1"], ["t2"]],
    )
    importer = exp_module.ExperimentsImporter(csv_path)

    calls = {"created": 0}

    def fake_create(row: Any, template: Any = None) -> str:
        calls["created"] += 1
        return "1"

    monkeypatch.setattr(importer, "create_new", fake_create)

    importer.create_all_from_csv()

    assert calls["created"] == 2


def test_create_all_from_csv_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(),
    )

    csv_path = write_csv(
        tmp_path / "exp.csv",
        ["experiment id", "title"],
        [["10", "t1"], ["", "t2"], ["20", "t3"]],
    )
    importer = exp_module.ExperimentsImporter(csv_path, update_existing=True)

    calls = {"patched": 0}

    def fake_patch(*args: Any, **kwargs: Any) -> int:
        calls["patched"] += 1
        return 200

    monkeypatch.setattr(importer, "patch_existing", fake_patch)

    ids = importer.create_all_from_csv()

    assert calls["patched"] == 2
    assert ids == ["10", "20"]
    assert importer.skipped_count == 1


def test_post_extra_fields_from_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(
            json_data={"metadata": {"extra_fields": {"Extra Field": {"type": "text"}}}}
        )

    captured: dict[str, dict[str, Any]] = {}

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs["data"]
        if not isinstance(data, dict):
            raise AssertionError("Expected dict payload for patch")
        captured["data"] = data
        return FakeResponse()

    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, patch=fake_patch),
    )

    csv_path = write_csv(
        tmp_path / "exp.csv",
        ["title", "extra field"],
        [["t", "value"]],
    )
    importer = exp_module.ExperimentsImporter(csv_path)

    row = importer.basic_df.iloc[0]
    importer.post_extra_fields_from_row("1", row, known_columns={"title"})

    assert "metadata" in captured["data"]


def test_coerce_select_field() -> None:
    defn = {"type": "select", "allow_multi_values": True, "options": ["A", "B"]}
    coerced = exp_module.ExperimentsImporter._coerce_for_field(defn, "a, B")
    assert coerced == ["A", "B"]
