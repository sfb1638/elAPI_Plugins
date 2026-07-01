from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.services.importers import experiments_importer as exp_module
from tests.conftest import FakeEndpoint, FakeResponse, write_csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_importer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    headers: list[str],
    rows: list[list[Any]],
    *,
    get: Any = None,
    post: Any = None,
    patch: Any = None,
    delete: Any = None,
    template_id: int | str | None = None,
    category_id: int | str | None = None,
    update_existing: bool = False,
    files_base_dir: str | Path | None = None,
) -> exp_module.ExperimentsImporter:
    """Create an ExperimentsImporter backed by a temporary CSV and fake endpoint."""
    _post = post or (lambda **kw: FakeResponse(headers={"Location": "http://x/experiments/99"}))
    _patch = patch or (lambda **kw: FakeResponse())
    _get = get or (lambda **kw: FakeResponse(json_data={"metadata": {"extra_fields": {}}}))
    _delete = delete or (lambda **kw: FakeResponse())

    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=_get, post=_post, patch=_patch, delete=_delete),
    )

    csv_path = write_csv(tmp_path / "exp.csv", headers, rows)
    return exp_module.ExperimentsImporter(
        csv_path,
        template_id=template_id,
        category_id=category_id,
        update_existing=update_existing,
        files_base_dir=files_base_dir,
    )


# ---------------------------------------------------------------------------
# create_new
# ---------------------------------------------------------------------------

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

    called = {"attach": 0, "extra": 0}

    def fake_attach(*args: Any, **kwargs: Any) -> None:
        called["attach"] += 1

    def fake_extra(*args: Any, **kwargs: Any) -> None:
        called["extra"] += 1

    monkeypatch.setattr(importer, "attach_files", fake_attach)
    monkeypatch.setattr(importer, "post_extra_fields_from_row", fake_extra)

    experiment_id = importer.create_new(importer.basic_df.iloc[0])

    assert experiment_id == "123"
    assert called["attach"] == 1
    assert called["extra"] == 1


def test_create_new_with_single_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When the path column points to a file, attach_files is called."""
    single_file = tmp_path / "report.pdf"
    single_file.write_text("data", encoding="utf-8")

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "attachments"],
        [["t", str(single_file)]],
    )

    called = {"attach": 0}

    monkeypatch.setattr(importer, "attach_files", lambda *a, **kw: called.__setitem__("attach", called["attach"] + 1))
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.create_new(importer.basic_df.iloc[0])

    assert called["attach"] == 1


def test_create_new_no_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When no path column is present, no file attachment methods are called."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["experiment1"]],
    )

    called = {"attach": 0}
    monkeypatch.setattr(importer, "attach_files", lambda *a, **kw: called.__setitem__("attach", 1))
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    eid = importer.create_new(importer.basic_df.iloc[0])

    assert eid == "99"
    assert called["attach"] == 0


def test_create_new_with_category(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """create_new patches category when default_category or CSV category is set."""
    patched_data: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        patched_data.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        patch=fake_patch,
        category_id="7",
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.create_new(importer.basic_df.iloc[0])

    category_patches = [d for d in patched_data if "category" in d]
    assert len(category_patches) == 1
    assert category_patches[0]["category"] == "7"


def test_create_new_with_template(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """create_new includes the template in the POST payload."""
    posted_data: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        posted_data.append(kwargs.get("data", {}))
        return FakeResponse(headers={"Location": "http://x/experiments/50"})

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fake_post,
        template_id=42,
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    eid = importer.create_new(importer.basic_df.iloc[0])

    assert eid == "50"
    assert any(d.get("template") == 42 for d in posted_data)


def test_create_new_with_tags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """create_new calls replace_tags when the row has a tags column."""
    tag_calls: list[list[str]] = []

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "tags"],
        [["t", "alpha,beta"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)
    monkeypatch.setattr(importer, "replace_tags", lambda rid, tags: tag_calls.append(tags))

    importer.create_new(importer.basic_df.iloc[0])

    assert len(tag_calls) == 1
    assert tag_calls[0] == ["alpha", "beta"]


def test_create_new_with_body(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """create_new includes body in POST payload."""
    posted: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        posted.append(kwargs.get("data", {}))
        return FakeResponse(headers={"Location": "http://x/experiments/1"})

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body"],
        [["t", "<p>hello</p>"]],
        post=fake_post,
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.create_new(importer.basic_df.iloc[0])

    assert any(d.get("body") == "<p>hello</p>" for d in posted)


def test_create_new_post_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """create_new raises RuntimeError when the initial POST fails."""
    def fail_post(**kwargs: Any) -> FakeResponse:
        return FakeResponse(status_code=500, text="Internal Server Error",
                            headers={"Location": "http://x/experiments/0"})

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fail_post,
    )

    with pytest.raises(RuntimeError, match="failed with status"):
        importer.create_new(importer.basic_df.iloc[0])


# ---------------------------------------------------------------------------
# patch_existing
# ---------------------------------------------------------------------------

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


def test_patch_existing_with_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """patch_existing attaches files when a path column points to a directory."""
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "data.csv").write_text("a,b", encoding="utf-8")

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "attachments"],
        [["t", str(files_dir)]],
    )

    called = {"attach": 0}
    monkeypatch.setattr(importer, "attach_files", lambda *a, **kw: called.__setitem__("attach", called["attach"] + 1))
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert called["attach"] == 1


def test_patch_existing_with_single_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """patch_existing calls attach_files when path points to a file."""
    single_file = tmp_path / "report.pdf"
    single_file.write_text("data", encoding="utf-8")

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "attachments"],
        [["t", str(single_file)]],
    )

    called = {"attach": 0}
    monkeypatch.setattr(importer, "attach_files", lambda *a, **kw: called.__setitem__("attach", called["attach"] + 1))
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert called["attach"] == 1


def test_patch_existing_with_string_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """patch_existing handles metadata stored as a JSON string."""
    metadata_str = json.dumps({"extra_fields": {"Field1": {"type": "text", "value": "old"}}})

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": metadata_str})

    captured: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        get=fake_get,
        patch=fake_patch,
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(captured) >= 1
    assert "metadata" in captured[0]
    patched_metadata = json.loads(captured[0]["metadata"])
    assert "Field1" in patched_metadata["extra_fields"]
    assert "field1" not in patched_metadata["extra_fields"]


def test_patch_existing_with_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """patch_existing includes normalized date in payload."""
    captured: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "date"],
        [["t", "15.03.2024"]],
        patch=fake_patch,
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    date_patches = [d for d in captured if "date" in d]
    assert len(date_patches) == 1
    assert date_patches[0]["date"] == "2024-03-15"


# ---------------------------------------------------------------------------
# patch_existing – $delete_V and $delete_F
# ---------------------------------------------------------------------------

def test_patch_existing_delete_V_clears_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_V in the body column clears the body in the patch payload."""
    captured: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body"],
        [["My Title", "$delete_V"]],
        patch=fake_patch,
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(captured) == 1
    assert captured[0]["body"] == ""
    assert captured[0]["title"] == "My Title"


def test_patch_existing_delete_F_removes_body_column(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_F in the body column drops it from the row; body NOT in payload."""
    captured: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body"],
        [["My Title", "$delete_F"]],
        patch=fake_patch,
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(captured) == 1
    assert "body" not in captured[0]
    assert captured[0]["title"] == "My Title"


def test_patch_existing_delete_V_extra_field_is_cleared(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_V clears the extra field value before metadata patching."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Custom Field"],
        [["t", "$delete_V"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    assert rows_received[0]["Custom Field"] == ""


def test_patch_existing_delete_F_extra_field_not_in_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_F drops the extra field column entirely; post_extra_fields_from_row never sees it."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Custom Field"],
        [["t", "$delete_F"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    assert "Custom Field" not in rows_received[0].index


def test_patch_existing_delete_V_clears_extra_field_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_V on an existing extra field patches its value to empty."""
    metadata = {"extra_fields": {"Custom Field": {"value": "old"}}}

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": json.dumps(metadata)})

    captured: list[dict[str, Any]] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if isinstance(data, dict):
            captured.append(data)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch,
        tmp_path,
        ["title", "Custom Field"],
        [["t", "$delete_V"]],
        get=fake_get,
        patch=fake_patch,
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    metadata_payloads = [data for data in captured if "metadata" in data]
    assert metadata_payloads
    patched_metadata = json.loads(metadata_payloads[-1]["metadata"])
    assert patched_metadata["extra_fields"]["Custom Field"]["value"] == ""


def test_patch_existing_delete_F_removes_extra_field_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_F on an existing extra field removes it from metadata."""
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

    importer = _make_importer(
        monkeypatch,
        tmp_path,
        ["title", "Custom Field", "Keep Field"],
        [["t", "$delete_F", "new keep"]],
        get=fake_get,
        patch=fake_patch,
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    metadata_payloads = [data for data in captured if "metadata" in data]
    assert metadata_payloads
    patched_metadata = json.loads(metadata_payloads[-1]["metadata"])
    assert "Custom Field" not in patched_metadata["extra_fields"]
    assert patched_metadata["extra_fields"]["Keep Field"]["value"] == "new keep"


def test_patch_existing_rename_extra_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """'$rename->New Name' renames the field key while preserving value and definition."""
    metadata = {
        "extra_fields": {
            "Custom Field": {"value": "keepme", "type": "text", "group_id": 3},
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

    importer = _make_importer(
        monkeypatch,
        tmp_path,
        ["title", "Custom Field"],
        [["t", "$rename->New Name"]],
        get=fake_get,
        patch=fake_patch,
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    metadata_payloads = [data for data in captured if "metadata" in data]
    assert metadata_payloads
    fields = json.loads(metadata_payloads[-1]["metadata"])["extra_fields"]
    assert "Custom Field" not in fields
    assert fields["New Name"] == {"value": "keepme", "type": "text", "group_id": 3}


def test_patch_existing_rename_collision_is_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Renaming onto an existing field name is skipped; neither field is clobbered."""
    metadata = {
        "extra_fields": {
            "Custom Field": {"value": "a"},
            "Target": {"value": "b"},
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

    importer = _make_importer(
        monkeypatch,
        tmp_path,
        ["title", "Custom Field"],
        [["t", "$rename->Target"]],
        get=fake_get,
        patch=fake_patch,
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    fields = json.loads(
        [d for d in captured if "metadata" in d][-1]["metadata"]
    )["extra_fields"]
    assert fields["Custom Field"] == {"value": "a"}
    assert fields["Target"] == {"value": "b"}


def test_patch_existing_rename_nonexistent_field_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Renaming a field that the entity does not have leaves metadata unchanged."""
    metadata = {"extra_fields": {"Keep": {"value": "v"}}}

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": json.dumps(metadata)})

    captured: list[dict[str, Any]] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if isinstance(data, dict):
            captured.append(data)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch,
        tmp_path,
        ["title", "Missing Field"],
        [["t", "$rename->Whatever"]],
        get=fake_get,
        patch=fake_patch,
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    payloads = [d for d in captured if "metadata" in d]
    if payloads:
        fields = json.loads(payloads[-1]["metadata"])["extra_fields"]
        assert fields == {"Keep": {"value": "v"}}


def test_extract_rename_map_requires_exact_prefix() -> None:
    """Only cells starting exactly with '$rename->' are treated as rename markers."""
    row = pd.Series(
        {
            "A": "$rename->New A",
            "B": " $rename->spaced",
            "C": "rename->no dollar",
            "D": "$rename->",
            "E": "normal",
        }
    )
    assert exp_module.ExperimentsImporter._extract_rename_map(row) == {"A": "New A"}


def test_patch_existing_delete_V_multiple_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Multiple columns with $delete_V are all cleared to empty string."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body", "Field A", "Field B"],
        [["t", "$delete_V", "$delete_V", "keep_me"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    captured: list[dict] = []
    original_patch = importer.endpoint.patch

    def spy_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    monkeypatch.setattr(importer.endpoint, "patch", spy_patch)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    assert rows_received[0]["Field A"] == ""
    assert rows_received[0]["Field B"] == "keep_me"
    # body cleared -> empty body payload
    assert any(d.get("body") == "" for d in captured)


def test_patch_existing_delete_F_multiple_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Multiple $delete_F columns are all dropped from the row."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Field A", "Field B", "Field C"],
        [["t", "$delete_F", "$delete_F", "keep_me"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    assert "Field A" not in rows_received[0].index
    assert "Field B" not in rows_received[0].index
    assert rows_received[0]["Field C"] == "keep_me"


def test_patch_existing_delete_V_and_delete_F_combined(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_V and $delete_F can be used together in the same row."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body", "Field A", "Field B"],
        [["t", "$delete_V", "$delete_F", "keep_me"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    captured: list[dict] = []

    def spy_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    monkeypatch.setattr(importer.endpoint, "patch", spy_patch)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    # delete_V cleared body -> empty body payload
    assert any(d.get("body") == "" for d in captured)
    # delete_F dropped Field A
    assert "Field A" not in rows_received[0].index
    # Field B untouched
    assert rows_received[0]["Field B"] == "keep_me"


def test_patch_existing_delete_V_title_unaffected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Title is extracted before $delete_V runs; title is still included in payload."""
    captured: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body"],
        [["Real Title", "$delete_V"]],
        patch=fake_patch,
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(captured) == 1
    assert captured[0]["title"] == "Real Title"
    assert captured[0]["body"] == ""


def test_patch_existing_normal_values_unaffected_by_delete_markers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Columns without $delete_V or $delete_F are passed through unchanged."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body", "Field A"],
        [["t", "some body text", "normal value"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    captured: list[dict] = []

    def spy_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    monkeypatch.setattr(importer.endpoint, "patch", spy_patch)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    assert rows_received[0]["Field A"] == "normal value"
    assert any(d.get("body") == "some body text" for d in captured)


def test_patch_existing_delete_V_tags_no_new_tags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_V on the tags column adds no new tags (existing tags are kept)."""
    tag_calls: list[list[str]] = []

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "tags"],
        [["t", "$delete_V"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)
    monkeypatch.setattr(
        importer, "append_tags", lambda rid, tags, **kw: tag_calls.append(tags)
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(tag_calls) == 1
    assert tag_calls[0] == []


def test_patch_existing_delete_F_tags_column_dropped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """$delete_F on the tags column drops it; append_tags is called with an empty list."""
    tag_calls: list[list[str]] = []

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "tags"],
        [["t", "$delete_F"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)
    monkeypatch.setattr(
        importer, "append_tags", lambda rid, tags, **kw: tag_calls.append(tags)
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(tag_calls) == 1
    assert tag_calls[0] == []


def test_patch_existing_body_appends_to_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A new body value is appended to the existing body, not overwritten."""
    captured: dict[str, Any] = {}

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(
            json_data={"body": "<p>old</p>", "metadata": {"extra_fields": {}}}
        )

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs.get("data")
        if isinstance(data, dict) and "body" in data:
            captured["body"] = data["body"]
        return FakeResponse()

    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, patch=fake_patch),
    )
    csv_path = write_csv(tmp_path / "exp.csv", ["title", "body"], [["t", "new text"]])
    importer = exp_module.ExperimentsImporter(csv_path)
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)
    monkeypatch.setattr(importer, "append_tags", lambda *a, **kw: None)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert captured["body"] == "<p>old</p>\nnew text"


def test_patch_existing_tags_appended_keeping_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """New tags are appended via append_tags; the existing tag string is passed through."""
    calls: list[dict[str, Any]] = []

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(
            json_data={"tags": "keep1|keep2", "metadata": {"extra_fields": {}}}
        )

    monkeypatch.setattr(
        exp_module,
        "get_fixed",
        lambda name: FakeEndpoint(get=fake_get, patch=lambda **kw: FakeResponse()),
    )
    csv_path = write_csv(tmp_path / "exp.csv", ["title", "tags"], [["t", "keep1,new"]])
    importer = exp_module.ExperimentsImporter(csv_path)
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)
    monkeypatch.setattr(
        importer,
        "append_tags",
        lambda rid, tags, **kw: calls.append({"tags": tags, "kw": kw}),
    )

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(calls) == 1
    assert calls[0]["tags"] == ["keep1", "new"]
    assert calls[0]["kw"]["existing_tags"] == "keep1|keep2"


def test_append_tags_skips_existing_and_posts_new(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """append_tags posts only tags not already present, without clearing existing ones."""
    posted: list[str] = []
    deleted: list[Any] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        posted.append(kwargs["data"]["tag"])
        return FakeResponse()

    def fake_delete(**kwargs: Any) -> FakeResponse:
        deleted.append(kwargs)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path, ["title"], [["t"]],
        post=fake_post, delete=fake_delete,
    )

    importer.append_tags("1", ["keep", "new1", "new2"], existing_tags="keep|other")

    assert posted == ["new1", "new2"]
    assert deleted == []


def test_patch_existing_delete_V_does_not_match_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cells with values similar to but not exactly '$delete_V' are not cleared."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Field A", "Field B"],
        [["t", "delete_V", " $delete_V "]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    # Neither partial match should be cleared
    assert rows_received[0]["Field A"] == "delete_V"
    assert rows_received[0]["Field B"] == " $delete_V "


def test_patch_existing_delete_F_does_not_match_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cells with values similar to but not exactly '$delete_F' are not dropped."""
    rows_received: list[pd.Series] = []

    def capturing_extra(eid: Any, row: pd.Series, **kwargs: Any) -> None:
        rows_received.append(row.copy())

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Field A", "Field B"],
        [["t", "delete_F", " $delete_F "]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", capturing_extra)

    importer.patch_existing("1", importer.basic_df.iloc[0])

    assert len(rows_received) == 1
    assert "Field A" in rows_received[0].index
    assert "Field B" in rows_received[0].index


# ---------------------------------------------------------------------------
# create_all_from_csv
# ---------------------------------------------------------------------------

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


def test_create_all_update_no_id_col_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """update_existing with no experiment ID column raises ValueError."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        update_existing=True,
    )

    # _experiment_id_col is None because there's no "experiment id" column
    with pytest.raises(ValueError, match="no 'Experiment ID' column"):
        importer.create_all_from_csv()


def test_create_all_update_skips_on_patch_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rows that fail to patch are skipped and counted."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["experiment id", "title"],
        [["10", "t1"], ["20", "t2"]],
        update_existing=True,
    )

    def fail_patch(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("API error")

    monkeypatch.setattr(importer, "patch_existing", fail_patch)

    ids = importer.create_all_from_csv()

    assert ids == []
    assert importer.skipped_count == 2


def test_create_all_from_csv_with_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Template argument is forwarded to create_new."""
    templates_received: list = []

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
    )

    def capture_create(row: Any, template: Any = None) -> str:
        templates_received.append(template)
        return "1"

    monkeypatch.setattr(importer, "create_new", capture_create)

    importer.create_all_from_csv(template=55)

    assert templates_received == [55]


# ---------------------------------------------------------------------------
# post_extra_fields_from_row
# ---------------------------------------------------------------------------

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


def test_post_extra_fields_no_matching_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When all CSV columns are known, no metadata patch is issued."""
    patch_called = {"count": 0}

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": {"extra_fields": {}}})

    def counting_patch(**kwargs: Any) -> FakeResponse:
        patch_called["count"] += 1
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        get=fake_get,
        patch=counting_patch,
    )

    row = importer.basic_df.iloc[0]
    importer.post_extra_fields_from_row("1", row, known_columns={"title"})

    assert patch_called["count"] == 0


def test_post_extra_fields_creates_new_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CSV columns not in elab extra_fields are added as new fields."""
    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": {"extra_fields": {}}})

    captured: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Custom Column"],
        [["t", "custom_val"]],
        get=fake_get,
        patch=fake_patch,
    )

    row = importer.basic_df.iloc[0]
    importer.post_extra_fields_from_row("1", row, known_columns={"title"})

    assert len(captured) == 1
    metadata = json.loads(captured[0]["metadata"])
    assert "Custom Column" in metadata["extra_fields"]
    assert metadata["extra_fields"]["Custom Column"]["value"] == "custom_val"


def test_post_extra_fields_with_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Link columns trigger _post_links and are not patched as metadata."""
    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": {"extra_fields": {}}})

    link_posts: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        link_posts.append(kwargs)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "experiments links"],
        [["t", "5, 10"]],
        get=fake_get,
        post=fake_post,
    )

    row = importer.basic_df.iloc[0]
    importer.post_extra_fields_from_row("1", row, known_columns={"title"})

    # Two links (5, 10) should each produce a post call
    assert len(link_posts) == 2
    sub_endpoints = [p["sub_endpoint_name"] for p in link_posts]
    assert all(s == "experiments_links" for s in sub_endpoints)


def test_post_extra_fields_with_items_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """'resources links' column maps to items_links sub-endpoint."""
    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": {"extra_fields": {}}})

    link_posts: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        link_posts.append(kwargs)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "resources links"],
        [["t", "3"]],
        get=fake_get,
        post=fake_post,
    )

    row = importer.basic_df.iloc[0]
    importer.post_extra_fields_from_row("1", row, known_columns={"title"})

    assert len(link_posts) == 1
    assert link_posts[0]["sub_endpoint_name"] == "items_links"


def test_post_extra_fields_string_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Metadata stored as JSON string is correctly parsed."""
    metadata_str = json.dumps({"extra_fields": {"My Field": {"type": "text", "value": ""}}})

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": metadata_str})

    captured: list[dict] = []

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data", {}))
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "my field"],
        [["t", "updated_val"]],
        get=fake_get,
        patch=fake_patch,
    )

    row = importer.basic_df.iloc[0]
    importer.post_extra_fields_from_row("1", row, known_columns={"title"})

    assert len(captured) == 1
    metadata = json.loads(captured[0]["metadata"])
    assert metadata["extra_fields"]["My Field"]["value"] == "updated_val"


def test_post_extra_fields_patch_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RuntimeError is raised when patch fails."""
    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"metadata": {"extra_fields": {}}})

    def fail_patch(**kwargs: Any) -> FakeResponse:
        return FakeResponse(status_code=500, text="Server Error")

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Custom Col"],
        [["t", "val"]],
        get=fake_get,
        patch=fail_patch,
    )

    row = importer.basic_df.iloc[0]
    with pytest.raises(RuntimeError, match="Failed to patch extra fields"):
        importer.post_extra_fields_from_row("1", row, known_columns={"title"})


# ---------------------------------------------------------------------------
# attach_files
# ---------------------------------------------------------------------------

def test_attach_files_single_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """attach_files with a single file delegates to attach_single_file (files[] format)."""
    posted: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        posted.append(kwargs)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fake_post,
    )

    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")

    importer.attach_files(1, f)

    assert len(posted) == 1
    assert posted[0]["sub_endpoint_name"] == "uploads"
    # attach_single_file uses files[] tuple format
    assert posted[0]["files"][0][0] == "files[]"


def test_attach_files_invalid_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Non-numeric ID raises ValueError."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
    )

    f = tmp_path / "doc.txt"
    f.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid entry ID"):
        importer.attach_files("abc", f)


def test_attach_files_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Missing path raises FileNotFoundError."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
    )

    with pytest.raises(FileNotFoundError, match="not found"):
        importer.attach_files(1, tmp_path / "nonexistent.txt")


def test_attach_files_single_file_failure_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Upload failure for a single file raises after both format attempts fail."""
    def fail_post(**kwargs: Any) -> FakeResponse:
        return FakeResponse(status_code=500, text="Server Error")

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fail_post,
    )

    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")

    with pytest.raises(Exception):
        importer.attach_files(1, f)


def test_attach_files_uploads_each_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each file in the directory is uploaded individually."""
    posted: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        posted.append(kwargs)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fake_post,
    )

    files_dir = tmp_path / "uploads"
    files_dir.mkdir()
    for i in range(3):
        (files_dir / f"file{i}.txt").write_text(f"content{i}", encoding="utf-8")

    importer.attach_files(1, files_dir)

    # One POST per file
    assert len(posted) == 3
    assert all(p["sub_endpoint_name"] == "uploads" for p in posted)


def test_attach_files_partial_failure_continues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When one file's first attempt fails, the fallback is tried and remaining files continue."""
    call_count = {"n": 0}

    def fake_post(**kwargs: Any) -> FakeResponse:
        call_count["n"] += 1
        if call_count["n"] == 2:
            return FakeResponse(status_code=500, text="Server Error")
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fake_post,
    )

    files_dir = tmp_path / "uploads"
    files_dir.mkdir()
    (files_dir / "a.txt").write_text("a", encoding="utf-8")
    (files_dir / "b.txt").write_text("b", encoding="utf-8")
    (files_dir / "c.txt").write_text("c", encoding="utf-8")

    # Should not raise; second file's first attempt fails but fallback succeeds
    importer.attach_files(1, files_dir)

    # file a: 1 call, file b: 2 calls (files[] fails + file fallback), file c: 1 call
    assert call_count["n"] == 4


def test_attach_files_empty_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No uploads when directory is empty."""
    posted: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        posted.append(kwargs)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fake_post,
    )

    files_dir = tmp_path / "empty"
    files_dir.mkdir()

    importer.attach_files(1, files_dir)

    assert len(posted) == 0


# ---------------------------------------------------------------------------
# _split_multi
# ---------------------------------------------------------------------------

def test_split_multi_comma() -> None:
    assert exp_module.ExperimentsImporter._split_multi("a, b, c") == ["a", "b", "c"]


def test_split_multi_semicolon() -> None:
    assert exp_module.ExperimentsImporter._split_multi("x; y") == ["x", "y"]


def test_split_multi_mixed() -> None:
    assert exp_module.ExperimentsImporter._split_multi("a, b; c") == ["a", "b", "c"]


def test_split_multi_nbsp() -> None:
    result = exp_module.ExperimentsImporter._split_multi("a\u00a0,\u00a0b")
    assert result == ["a", "b"]


def test_split_multi_empty() -> None:
    assert exp_module.ExperimentsImporter._split_multi("") == []


def test_split_multi_whitespace_only() -> None:
    assert exp_module.ExperimentsImporter._split_multi("  ,  , ") == []


# ---------------------------------------------------------------------------
# _parse_link_ids
# ---------------------------------------------------------------------------

def test_parse_link_ids_basic() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids("1, 2, 3") == [1, 2, 3]


def test_parse_link_ids_none() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids(None) == []


def test_parse_link_ids_nan() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids(float("nan")) == []


def test_parse_link_ids_empty_string() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids("") == []


def test_parse_link_ids_floats() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids("1.0, 2.0") == [1, 2]


def test_parse_link_ids_negative_skipped() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids("-1, 5") == [5]


def test_parse_link_ids_duplicates_removed() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids("3, 3, 5") == [3, 5]


def test_parse_link_ids_non_numeric_skipped() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids("abc, 7") == [7]


def test_parse_link_ids_semicolons() -> None:
    assert exp_module.ExperimentsImporter._parse_link_ids("1; 2; 3") == [1, 2, 3]


# ---------------------------------------------------------------------------
# _coerce_for_field
# ---------------------------------------------------------------------------

def test_coerce_select_field() -> None:
    defn = {"type": "select", "allow_multi_values": True, "options": ["A", "B"]}
    coerced = exp_module.ExperimentsImporter._coerce_for_field(defn, "a, B")
    assert coerced == ["A", "B"]


def test_coerce_single_select() -> None:
    defn = {"type": "select", "options": ["Red", "Green", "Blue"]}
    assert exp_module.ExperimentsImporter._coerce_for_field(defn, "green") == "Green"


def test_coerce_single_select_exact() -> None:
    defn = {"type": "select", "options": ["Red", "Green"]}
    assert exp_module.ExperimentsImporter._coerce_for_field(defn, "Red") == "Red"


def test_coerce_single_select_no_match() -> None:
    defn = {"type": "select", "options": ["Red", "Green"]}
    assert exp_module.ExperimentsImporter._coerce_for_field(defn, "Purple") is None


def test_coerce_non_select() -> None:
    defn = {"type": "text"}
    assert exp_module.ExperimentsImporter._coerce_for_field(defn, "hello") == "hello"


def test_coerce_none_defn() -> None:
    assert exp_module.ExperimentsImporter._coerce_for_field(None, "val") == "val"


def test_coerce_empty_defn() -> None:
    assert exp_module.ExperimentsImporter._coerce_for_field({}, "val") == "val"


def test_coerce_multi_select_preserves_order() -> None:
    defn = {"type": "select", "allow_multi_values": True, "options": ["C", "B", "A"]}
    result = exp_module.ExperimentsImporter._coerce_for_field(defn, "A, C")
    assert result == ["A", "C"]


def test_coerce_multi_select_no_duplicates() -> None:
    defn = {"type": "select", "allow_multi_values": True, "options": ["A", "B"]}
    result = exp_module.ExperimentsImporter._coerce_for_field(defn, "a, A, b")
    assert result == ["A", "B"]


# ---------------------------------------------------------------------------
# _collect_csv_extra_fields
# ---------------------------------------------------------------------------

def test_collect_csv_extra_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Custom Col", "Another"],
        [["t", "val1", "val2"]],
    )

    row = importer.basic_df.iloc[0]
    extras = importer._collect_csv_extra_fields(row, known_columns={"title"})

    assert len(extras) == 2
    values = {v[1] for v in extras.values()}
    assert values == {"val1", "val2"}


def test_collect_csv_extra_fields_skips_nan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "Custom Col"],
        [["t", ""]],
    )

    row = importer.basic_df.iloc[0]
    extras = importer._collect_csv_extra_fields(row, known_columns={"title"})

    # Empty string is stripped, so no extras
    assert len(extras) == 0


def test_collect_csv_extra_fields_skips_known(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Known post fields are excluded from extras."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "tags", "Custom"],
        [["t", "a", "v"]],
    )

    row = importer.basic_df.iloc[0]
    extras = importer._collect_csv_extra_fields(row)

    # title and tags are known fields, Custom is not
    canon_keys = list(extras.keys())
    assert len(canon_keys) == 1


# ---------------------------------------------------------------------------
# _find_experiment_id_col
# ---------------------------------------------------------------------------

def test_find_experiment_id_col(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["Experiment ID", "title"],
        [["1", "t"]],
        update_existing=True,
    )

    assert importer._experiment_id_col == "Experiment ID"


def test_find_experiment_id_col_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body"],
        [["t", "b"]],
    )

    assert importer._find_entity_id_col("experimentid") is None


# ---------------------------------------------------------------------------
# _parse_entity_id (experiment context)
# ---------------------------------------------------------------------------

def test_parse_experiment_id_valid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["experiment id", "title"],
        [["42", "t"]],
        update_existing=True,
    )

    row = importer.basic_df.iloc[0]
    assert importer._parse_entity_id(importer._experiment_id_col, row, 0, "Experiment") == "42"


def test_parse_experiment_id_float(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["experiment id", "title"],
        [["42.0", "t"]],
        update_existing=True,
    )

    row = importer.basic_df.iloc[0]
    assert importer._parse_entity_id(importer._experiment_id_col, row, 0, "Experiment") == "42"


def test_parse_experiment_id_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["experiment id", "title"],
        [["abc", "t"]],
        update_existing=True,
    )

    row = importer.basic_df.iloc[0]
    assert importer._parse_entity_id(importer._experiment_id_col, row, 0, "Experiment") is None


def test_parse_experiment_id_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["experiment id", "title"],
        [["", "t"]],
        update_existing=True,
    )

    row = importer.basic_df.iloc[0]
    assert importer._parse_entity_id(importer._experiment_id_col, row, 0, "Experiment") is None


def test_parse_experiment_id_no_col(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When id_col is None, returns None."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
    )

    row = importer.basic_df.iloc[0]
    assert importer._parse_entity_id(None, row, 0, "Experiment") is None


# ---------------------------------------------------------------------------
# _extract_known_post_fields
# ---------------------------------------------------------------------------

def test_extract_known_post_fields_with_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body"],
        [["t", "b"]],
        template_id=10,
    )

    row = importer.basic_df.iloc[0]
    data = importer._extract_known_post_fields(row, template=None)

    assert data["template"] == 10
    assert data["body"] == "b"


def test_extract_known_post_fields_override_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "body"],
        [["t", "b"]],
        template_id=10,
    )

    row = importer.basic_df.iloc[0]
    data = importer._extract_known_post_fields(row, template=99)

    assert data["template"] == 99


def test_extract_known_post_fields_no_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
    )

    row = importer.basic_df.iloc[0]
    data = importer._extract_known_post_fields(row, template=None)

    assert "body" not in data
    assert "template" not in data


# ---------------------------------------------------------------------------
# Constructor / properties
# ---------------------------------------------------------------------------

def test_constructor_with_category(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        category_id="5",
    )

    assert importer._default_category == "5"


def test_constructor_invalid_category_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="numeric"):
        _make_importer(
            monkeypatch, tmp_path,
            ["title"],
            [["t"]],
            category_id="abc",
        )


def test_constructor_with_files_base_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        files_base_dir=str(tmp_path),
    )

    assert importer.files_base_dir == tmp_path


def test_properties(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
    )

    assert importer.new_count == 0
    assert importer.patched_count == 0
    assert importer.skipped_count == 0
    assert len(importer.basic_df) == 1
    assert isinstance(importer.cols_canon, dict)
    assert importer.endpoint is not None


def test_counters_increment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """new_count increments after create_new calls."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t1"], ["t2"]],
    )
    monkeypatch.setattr(importer, "post_extra_fields_from_row", lambda *a, **kw: None)

    importer.create_new(importer.basic_df.iloc[0])
    importer.create_new(importer.basic_df.iloc[1])

    assert importer.new_count == 2


# ---------------------------------------------------------------------------
# Column normalization (NBSP, tabs)
# ---------------------------------------------------------------------------

def test_column_nbsp_normalized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """NBSP characters in column names are replaced with spaces."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "extra\u00a0field"],
        [["t", "v"]],
    )

    # The NBSP should have been normalized to a space
    assert "extra field" in importer.basic_df.columns


def test_column_tab_normalized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tab characters in column names are replaced with spaces."""
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title", "extra\tfield"],
        [["t", "v"]],
    )

    assert "extra field" in importer.basic_df.columns


# ---------------------------------------------------------------------------
# _post_links
# ---------------------------------------------------------------------------

def test_post_links_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    posted: list[dict] = []

    def fake_post(**kwargs: Any) -> FakeResponse:
        posted.append(kwargs)
        return FakeResponse()

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fake_post,
    )

    importer._post_links("1", [("experiments_links", [5, 10])])

    assert len(posted) == 2
    assert posted[0]["sub_endpoint_id"] == 5
    assert posted[1]["sub_endpoint_id"] == 10


def test_post_links_failure_logged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Link creation failures are logged but don't raise."""
    def fail_post(**kwargs: Any) -> FakeResponse:
        return FakeResponse(status_code=500, text="Error")

    importer = _make_importer(
        monkeypatch, tmp_path,
        ["title"],
        [["t"]],
        post=fail_post,
    )

    # Should not raise
    importer._post_links("1", [("experiments_links", [5])])
