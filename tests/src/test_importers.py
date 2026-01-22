from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.services.importers.base_importer import BaseImporter
from src.services.importers.resources_importer import ResourcesImporter
from tests.conftest import FakeEndpoint, FakeResponse


class DummyEndpoint(FakeEndpoint):
    def __init__(self) -> None:
        super().__init__(get=None, post=None, patch=None)
        self.last_patch: dict[str, Any] | None = None
        self.last_post_payload: dict[str, Any] | None = None

    def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        return FakeResponse(json_data={"id": 1})

    def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
        self.last_post_payload = kwargs.get("data")
        return FakeResponse(status_code=201, headers={"Location": "/items/10"})

    def patch(self, *args: Any, **kwargs: Any) -> FakeResponse:
        self.last_patch = kwargs.get("data")
        return FakeResponse(status_code=200)


class DummyImporter(BaseImporter):
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self._cols = self._canonicalize_column_indexes(df.columns)
        self._endpoint = DummyEndpoint()

    @property
    def basic_df(self) -> pd.DataFrame:
        return self._df

    @property
    def cols_canon(self) -> dict[str, str]:
        return self._cols

    @property
    def endpoint(self) -> DummyEndpoint:
        return self._endpoint

    @property
    def files_base_dir(self) -> Path | None:  # override to enable _resolve_folder join
        return Path("/base")


def test_base_importer_get_category_and_tags() -> None:
    df = pd.DataFrame([{"Category ID": "5", "tags": "a; b"}])
    importer = DummyImporter(df)
    row = df.iloc[0]

    cid = importer.get_category_id(row)
    assert cid == "5"
    assert importer.get_tags(row) == ["a", "b"]


def test_base_importer_canonicalize_and_find_col() -> None:
    importer = DummyImporter(pd.DataFrame(columns=["Body Text", "title"]))
    mapping = importer._canonicalize_column_indexes(importer.basic_df.columns)
    # The canonical key 'bodytext' should map to the original column name
    assert mapping["bodytext"] == "Body Text"
    assert importer._find_col_like("body") == "Body Text"


def test_base_importer_normalize_date_and_title(monkeypatch: pytest.MonkeyPatch) -> None:
    df = pd.DataFrame([{"Date": "01/02/2024", "Title": "  Hello  "}])
    importer = DummyImporter(df)
    row = df.iloc[0]
    normalized = importer._normalize_date(row)
    assert normalized == "2024-02-01"
    assert importer._get_title(row) == "Hello"


def test_base_importer_get_elab_id_and_validate_category() -> None:
    importer = DummyImporter(pd.DataFrame([{"Category": "x"}]))
    with pytest.raises(ValueError):
        importer.validate_category_id("abc")

    resp = FakeResponse(headers={"Location": "http://host/items/42"})
    assert importer.get_elab_id(resp) == "42"


def test_base_importer_resolve_folder_with_base_dir() -> None:
    importer = DummyImporter(pd.DataFrame([{"files_path": "folder/file.txt"}]))
    resolved = importer._resolve_folder("folder/file.txt")
    assert resolved == Path("/base/folder/file.txt")


def test_resources_importer_create_new(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    csv_path = tmp_path / "res.csv"
    csv_path.write_text("title,tags,category\nHello,tag1,1\n", encoding="utf-8")

    importer = ResourcesImporter(csv_path=csv_path)
    dummy_endpoint = DummyEndpoint()
    importer._endpoint = dummy_endpoint

    # Avoid network/file uploads during test
    monkeypatch.setattr(
        importer,
        "post_extra_fields_from_row",
        lambda *args, **kwargs: None,
    )

    new_id = importer.create_new(row=importer.basic_df.iloc[0], template=None)

    assert new_id == "10"
    assert dummy_endpoint.last_post_payload is not None
    assert dummy_endpoint.last_post_payload["title"] == "Hello"


def test_resources_importer_attach_single_file_missing(tmp_path: Path) -> None:
    csv_path = tmp_path / "res.csv"
    csv_path.write_text("title\nA\n", encoding="utf-8")
    importer = ResourcesImporter(csv_path=csv_path)
    importer._endpoint = DummyEndpoint()
    with pytest.raises(FileNotFoundError):
        importer.attach_single_file(resource_id=1, file=tmp_path / "missing.txt")


def test_resources_importer_post_extra_fields_patches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    df = pd.DataFrame([{"Color": "red"}])
    importer = object.__new__(ResourcesImporter)
    importer._resources_df = df
    importer._cols_canon = {"color": "Color"}
    importer._endpoint = DummyEndpoint()
    importer._template_id = None
    importer._files_base_dir = None
    importer._category_col = None
    importer._new_resources_counter = 0
    importer._patched_resources_counter = 0

    def fake_existing(elab_id: str) -> dict[str, Any]:
        _ = elab_id
        return {
            "metadata": {
                "extra_fields": {
                    "Color": {"type": "select", "options": ["Red", "Blue"]}
                }
            }
        }

    monkeypatch.setattr(importer, "get_existing_json", fake_existing)

    importer.post_extra_fields_from_row(
        resource_id="1",
        row=df.iloc[0],
        known_columns={"title"},
    )

    assert importer._endpoint.last_patch is not None
    payload = importer._endpoint.last_patch
    assert isinstance(payload, dict)
    metadata = json.loads(payload["metadata"])
    assert metadata["extra_fields"]["Color"]["value"] == "Red"


def test_resources_importer_creates_missing_extra_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    df = pd.DataFrame([{"New Field": "abc"}])
    importer = object.__new__(ResourcesImporter)
    importer._resources_df = df
    importer._cols_canon = {"newfield": "New Field"}
    importer._endpoint = DummyEndpoint()
    importer._template_id = None
    importer._files_base_dir = None
    importer._category_col = None
    importer._new_resources_counter = 0
    importer._patched_resources_counter = 0

    monkeypatch.setattr(importer, "get_existing_json", lambda _elab_id: {})

    importer.post_extra_fields_from_row(
        resource_id="1",
        row=df.iloc[0],
        known_columns={"title"},
    )

    assert importer._endpoint.last_patch is not None
    payload = importer._endpoint.last_patch
    metadata = json.loads(payload["metadata"])
    assert metadata["extra_fields"]["New Field"]["value"] == "abc"


def test_resources_importer_patch_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    importer = object.__new__(ResourcesImporter)
    importer._resources_df = pd.DataFrame([{"title": "T"}])
    importer._cols_canon = {"title": "title"}
    importer._endpoint = DummyEndpoint()
    importer._template_id = None
    importer._files_base_dir = None
    importer._category_col = None
    importer._new_resources_counter = 0
    importer._patched_resources_counter = 0

    def fake_existing(_elab_id: str) -> dict[str, Any]:
        return {"metadata": json.dumps({"extra_fields": {"Field": {"value": "v"}}})}

    monkeypatch.setattr(importer, "get_existing_json", fake_existing)

    status = importer.patch_existing(
        resource_id="1", row=importer.basic_df.iloc[0], category="2"
    )
    assert status == 200
    assert importer._endpoint.last_patch is not None


def test_resources_importer_coerce_for_field_select_multi() -> None:
    definition = {
        "type": "select",
        "options": ["Red", "Blue"],
        "allow_multi_values": True,
    }
    coerced = ResourcesImporter._coerce_for_field(definition, "red,blue,blue")
    assert coerced == ["Red", "Blue"]


def test_resources_importer_split_multi_trims_and_splits() -> None:
    parts = ResourcesImporter._split_multi(" one ; two,three ")
    assert parts == ["one", "two", "three"]


def test_resources_importer_link_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    df = pd.DataFrame(
        [
            {
                "Experiments Links": "1, 2.0",
                "Resources Link": "5,5,6",
                "title": "linked",
            }
        ]
    )
    importer = object.__new__(ResourcesImporter)
    importer._resources_df = df
    importer._cols_canon = {
        "experimentslinks": "Experiments Links",
        "resourceslink": "Resources Link",
        "title": "title",
    }
    importer._KNOWN_POST_FIELDS = set()  # ensure link columns treated as extras
    importer._endpoint = DummyEndpoint()
    importer._template_id = None
    importer._files_base_dir = None
    importer._category_col = None
    importer._new_resources_counter = 0
    importer._patched_resources_counter = 0

    monkeypatch.setattr(importer, "get_existing_json", lambda _elab_id: {})

    posted: list[tuple[str, list[int]]] = []

    def fake_post_links(rid: str, ops: list[tuple[str, list[int]]]) -> None:
        posted.extend(ops)

    importer._post_links = fake_post_links  # type: ignore[attr-defined]

    importer.post_extra_fields_from_row(
        resource_id="1",
        row=df.iloc[0],
        known_columns={"title"},
    )

    assert posted == [("experiments_links", [1, 2]), ("items_links", [5, 6])]
    # No metadata patch should be sent when only links are present
    assert importer._endpoint.last_patch is None
