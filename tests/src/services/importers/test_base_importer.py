from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.services.importers.base_importer import BaseImporter
from tests.conftest import FakeEndpoint, FakeResponse


class DummyImporter(BaseImporter):
    def __init__(self, df: pd.DataFrame, files_base_dir: Path | None = None) -> None:
        self._df = df
        self._cols_canon = {c.lower().replace(" ", ""): c for c in df.columns}
        self._files_base_dir = files_base_dir
        self._endpoint = FakeEndpoint()

    @property
    def basic_df(self) -> pd.DataFrame:
        return self._df

    @property
    def cols_canon(self) -> dict[str, str]:
        return self._cols_canon

    @property
    def endpoint(self) -> FakeEndpoint:
        return self._endpoint

    @property
    def files_base_dir(self) -> Path | None:
        return self._files_base_dir


def test_normalize_id() -> None:
    df = pd.DataFrame({"id": [1]})
    imp = DummyImporter(df)
    assert imp.normalize_id(None) is None
    assert imp.normalize_id(float("nan")) is None
    assert imp.normalize_id(1.0) == "1"
    assert imp.normalize_id("  ") is None


def test_get_tags_parsing() -> None:
    df = pd.DataFrame({"Tags": ["a,b"]})
    imp = DummyImporter(df)
    row = pd.Series({"Tags": "a; b | c"})
    imp._cols_canon = {"tags": "Tags"}
    tags = imp.get_tags(row)
    assert tags == ["a", "b | c"] or tags == ["a", "b", "c"]


def test_get_category_id() -> None:
    df = pd.DataFrame({"Category ID": ["12"]})
    imp = DummyImporter(df)
    row = pd.Series({"Category ID": "12"})
    assert imp.get_category_id(row) == "12"
    with pytest.raises(ValueError):
        imp.get_category_id(pd.Series({"Category ID": "abc"}))


def test_find_col_like() -> None:
    df = pd.DataFrame({"Body Text": ["x"], "Title": ["y"]})
    imp = DummyImporter(df)
    assert imp._find_col_like("body") == "Body Text"
    assert imp._find_col_like("title") == "Title"


def test_find_col_like_matches_whole_words_only() -> None:
    """'body' matches 'Main Body'/'body_content' but not 'Antibody' (suffix only)."""
    imp = DummyImporter(pd.DataFrame({"Main Body": ["x"], "Title": ["y"]}))
    assert imp._find_col_like("body") == "Main Body"

    imp = DummyImporter(pd.DataFrame({"body_content": ["x"]}))
    assert imp._find_col_like("body") == "body_content"

    # 'body' is only a suffix of 'antibody' -> must NOT be treated as the body col.
    imp = DummyImporter(pd.DataFrame({"Antibody conc": ["x"], "Title": ["y"]}))
    assert imp._find_col_like("body") is None


def test_find_path_col_is_case_and_whitespace_insensitive() -> None:
    df = pd.DataFrame({"Files Path": ["folder"], "Title": ["y"]})
    imp = DummyImporter(df)
    assert imp._find_path_col() == "Files Path"

    df = pd.DataFrame({"ATTACHMENTS": ["folder"], "Title": ["y"]})
    imp = DummyImporter(df)
    assert imp._find_path_col() == "ATTACHMENTS"


def test_resolve_folder_with_base(tmp_path: Path) -> None:
    df = pd.DataFrame({"id": [1]})
    imp = DummyImporter(df, files_base_dir=tmp_path)
    resolved = imp._resolve_folder("subdir/file.txt")
    assert resolved == (tmp_path / "subdir" / "file.txt").resolve()


def test_patch_decoded_extra_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    df = pd.DataFrame({"Extra Field": ["value"]})
    imp = DummyImporter(df)

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(
            json_data={
                "metadata_decoded": {
                    "extra_fields": [{"title": "Extra Field", "value": ""}]
                }
            }
        )

    captured: dict[str, dict[str, Any]] = {}

    def fake_patch(**kwargs: Any) -> FakeResponse:
        data = kwargs["data"]
        if not isinstance(data, dict):
            raise AssertionError("Expected dict payload for patch")
        captured["data"] = data
        return FakeResponse()

    imp._endpoint = FakeEndpoint(get=fake_get, patch=fake_patch)
    row = pd.Series({"Extra Field": "updated"})

    imp.patch_decoded_extra_fields("1", row, known_columns=set())
    assert "metadata" in captured["data"]


def test_patch_decoded_link_field_uses_id_string() -> None:
    df = pd.DataFrame({"Cloning Experiment ID": [22576.0, None]})
    imp = DummyImporter(df)

    def fake_get(**kwargs: Any) -> FakeResponse:
        return FakeResponse(
            json_data={
                "metadata_decoded": {
                    "extra_fields": [
                        {
                            "title": "Cloning Experiment ID",
                            "type": "experiments",
                            "value": "",
                        }
                    ]
                }
            }
        )

    captured: dict[str, dict[str, Any]] = {}

    def fake_patch(**kwargs: Any) -> FakeResponse:
        captured["data"] = kwargs["data"]
        return FakeResponse()

    imp._endpoint = FakeEndpoint(get=fake_get, patch=fake_patch)
    imp.patch_decoded_extra_fields("1", df.iloc[0], known_columns=set())

    field = captured["data"]["metadata"]["extra_fields"][0]
    # eLabFTW needs the linked id as a JSON string, not a number.
    assert field["value"] == "22576"
    assert isinstance(field["value"], str)
