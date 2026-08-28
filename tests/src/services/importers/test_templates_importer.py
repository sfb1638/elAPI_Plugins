from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.factories import ImporterFactory
from src.services.importers import templates_importer as tpl_module
from tests.conftest import FakeEndpoint, FakeResponse, write_csv

EXISTING_TEMPLATE: dict[str, Any] = {
    "title": "Old title",
    "body": "<p>OLD BODY</p>",
    "tags": None,
    "metadata": json.dumps(
        {
            "extra_fields": {
                "Species": {"type": "text", "value": "old"},
                "Obsolete": {"type": "text", "value": "x"},
            }
        }
    ),
}


def _make_importer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    headers: list[str],
    values: list[Any],
    captured: list[dict],
    sub_posts: list[str],
    kind: str = "resource_templates",
    update_existing: bool = True,
) -> Any:
    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data=EXISTING_TEMPLATE)

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs.get("data") or {})
        return FakeResponse()

    def fake_post(**kwargs: Any) -> FakeResponse:
        if kwargs.get("sub_endpoint_name"):
            sub_posts.append(kwargs["sub_endpoint_name"])
        return FakeResponse(headers={"Location": "http://x/items_types/99"})

    monkeypatch.setattr(
        tpl_module,
        "get_fixed",
        lambda name: FakeEndpoint(
            get=fake_get, patch=fake_patch, post=fake_post,
            delete=lambda **k: FakeResponse(),
        ),
    )
    csv_path = write_csv(tmp_path / "tpl.csv", headers, [values])
    return ImporterFactory.get_importer(
        kind, csv_path, update_existing=update_existing
    )


def _metadata_fields(captured: list[dict]) -> dict[str, Any]:
    payloads = [d for d in captured if "metadata" in d]
    assert payloads, "expected a metadata patch"
    return json.loads(payloads[-1]["metadata"])["extra_fields"]


def test_factory_knows_both_template_kinds() -> None:
    assert "resource_templates" in ImporterFactory._importers
    assert "experiment_templates" in ImporterFactory._importers


def test_unknown_template_kind_is_rejected(tmp_path: Path) -> None:
    csv_path = write_csv(tmp_path / "t.csv", ["title"], [["x"]])
    with pytest.raises(ValueError, match="Unknown template kind"):
        tpl_module.TemplatesImporter(csv_path, kind="nope")


def test_patch_template_title_body_and_extra_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Title overwrites, body appends, extra fields update — as for entries."""
    captured: list[dict] = []
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["Template ID", "title", "body", "Species"],
        ["263", "New title", "EXTRA", "cerevisiae"],
        captured, [],
    )

    importer.create_all_from_csv()

    entry = next(d for d in captured if "title" in d)
    assert entry["title"] == "New title"
    assert entry["body"] == "<p>OLD BODY</p>\nEXTRA"
    assert _metadata_fields(captured)["Species"]["value"] == "cerevisiae"


def test_template_markers_rename_and_delete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[dict] = []
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["Template ID", "Species", "Obsolete"],
        ["38", "$rename$Spezies", "$delete_F"],
        captured, [], kind="experiment_templates",
    )

    importer.create_all_from_csv()

    fields = _metadata_fields(captured)
    assert fields["Spezies"]["value"] == "old"
    assert "Species" not in fields
    assert "Obsolete" not in fields


def test_template_permissions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[dict] = []
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["Template ID", "canread_base", "canwrite_users"],
        ["263", "team", "351"],
        captured, [],
    )

    importer.create_all_from_csv()

    entry = next(d for d in captured if "canread_base" in d)
    assert entry["canread_base"] == 30
    assert json.loads(entry["canwrite"])["users"] == [351]


def test_templates_ignore_attachments_and_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Templates have no uploads/links endpoints: no requests, no stray fields."""
    captured: list[dict] = []
    sub_posts: list[str] = []
    importer = _make_importer(
        monkeypatch, tmp_path,
        ["Template ID", "attachments", "experiments links"],
        ["263", "/tmp/somewhere", "5,6"],
        captured, sub_posts,
    )

    importer.create_all_from_csv()

    assert sub_posts == []
    for data in captured:
        if "metadata" in data:
            fields = json.loads(data["metadata"])["extra_fields"]
            assert "attachments" not in fields
            assert not [k for k in fields if "link" in k.lower()]


def test_update_without_id_column_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    importer = _make_importer(
        monkeypatch, tmp_path, ["title"], ["x"], [], [],
    )
    with pytest.raises(ValueError, match="Template ID"):
        importer.create_all_from_csv()
