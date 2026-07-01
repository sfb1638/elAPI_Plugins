from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.services.importers import resources_importer as res_module
from tests.conftest import FakeEndpoint, FakeResponse, write_csv


def test_create_new_with_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_post(**kwargs: Any) -> FakeResponse:
        return FakeResponse(headers={"Location": "http://x/resources/99"})

    monkeypatch.setattr(
        res_module, "get_fixed", lambda name: FakeEndpoint(post=fake_post)
    )

    files_dir = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "a.txt").write_text("x", encoding="utf-8")

    csv_path = write_csv(
        tmp_path / "res.csv",
        ["title", "attachments"],
        [["t", str(files_dir)]],
    )
    importer = res_module.ResourcesImporter(csv_path)

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

    resource_id = importer.create_new(importer.basic_df.iloc[0])

    assert resource_id == "99"
    assert called["attach"] == 1
    assert called["single"] == 0
    assert called["extra"] == 1


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
        res_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, patch=fake_patch),
    )

    csv_path = write_csv(
        tmp_path / "res.csv",
        ["title", "extra field"],
        [["t", "value"]],
    )
    importer = res_module.ResourcesImporter(csv_path)

    row = importer.basic_df.iloc[0]
    importer.post_extra_fields_from_row("1", row, known_columns={"title"})

    assert "metadata" in captured["data"]


def test_patch_existing_preserves_extra_field_name_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = {"extra_fields": {"Mixed Case Field": {"value": "old"}}}

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": metadata})

    captured: list[dict[str, Any]] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if isinstance(data, dict):
            captured.append(data)
        return FakeResponse()

    monkeypatch.setattr(
        res_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, patch=fake_patch),
    )

    csv_path = write_csv(tmp_path / "res.csv", ["title"], [["t"]])
    importer = res_module.ResourcesImporter(csv_path)
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    metadata_payloads = [data for data in captured if "metadata" in data]
    assert metadata_payloads
    patched_metadata = json.loads(metadata_payloads[0]["metadata"])
    assert "Mixed Case Field" in patched_metadata["extra_fields"]
    assert "mixed case field" not in patched_metadata["extra_fields"]


def test_patch_existing_delete_V_clears_extra_field_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = {"extra_fields": {"Custom Field": {"value": "old"}}}

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": json.dumps(metadata)})

    captured: list[dict[str, Any]] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if isinstance(data, dict):
            captured.append(data)
        return FakeResponse()

    monkeypatch.setattr(
        res_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, patch=fake_patch),
    )

    csv_path = write_csv(
        tmp_path / "res.csv", ["title", "Custom Field"], [["t", "$delete_V"]]
    )
    importer = res_module.ResourcesImporter(csv_path)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    metadata_payloads = [data for data in captured if "metadata" in data]
    assert metadata_payloads
    patched_metadata = json.loads(metadata_payloads[-1]["metadata"])
    assert patched_metadata["extra_fields"]["Custom Field"]["value"] == ""


def test_patch_existing_delete_F_removes_extra_field_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = {
        "extra_fields": {
            "Custom Field": {"value": "old"},
            "Keep Field": {"value": "keep"},
        }
    }

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": json.dumps(metadata)})

    captured: list[dict[str, Any]] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if isinstance(data, dict):
            captured.append(data)
        return FakeResponse()

    monkeypatch.setattr(
        res_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, patch=fake_patch),
    )

    csv_path = write_csv(
        tmp_path / "res.csv",
        ["title", "Custom Field", "Keep Field"],
        [["t", "$delete_F", "new keep"]],
    )
    importer = res_module.ResourcesImporter(csv_path)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    metadata_payloads = [data for data in captured if "metadata" in data]
    assert metadata_payloads
    patched_metadata = json.loads(metadata_payloads[-1]["metadata"])
    assert "Custom Field" not in patched_metadata["extra_fields"]
    assert patched_metadata["extra_fields"]["Keep Field"]["value"] == "new keep"


def test_coerce_select_field() -> None:
    defn = {"type": "select", "allow_multi_values": True, "options": ["A", "B"]}
    coerced = res_module.ResourcesImporter._coerce_for_field(defn, "a, B")
    assert coerced == ["A", "B"]
