from __future__ import annotations

import json
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


# region --- validate_row ---


def _patch_lookup(
    monkeypatch: pytest.MonkeyPatch, statuses: dict[tuple[str, int], int]
) -> list[tuple[str, int]]:
    """Make get_fixed answer GETs from ``statuses``; return the calls made."""
    calls: list[tuple[str, int]] = []

    def fake_get_fixed(name: str) -> FakeEndpoint:
        def get(endpoint_id: int, **_: Any) -> FakeResponse:
            calls.append((name, endpoint_id))
            return FakeResponse(status_code=statuses.get((name, endpoint_id), 404))

        return FakeEndpoint(get=get)

    monkeypatch.setattr("src.services.importers.base_importer.get_fixed", fake_get_fixed)
    return calls


def test_validate_row_accepts_existing_links(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lookup(monkeypatch, {("experiments", 5): 200, ("resources", 7): 200})
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    row = pd.Series({"Experiments Links": "5", "Resources_Links": "7"})
    assert imp.validate_row(row) == []


def test_validate_row_flags_missing_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lookup(monkeypatch, {("experiments", 5): 200})
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    issues = imp.validate_row(pd.Series({"experiments links": "5, 99"}))
    assert [(i.column, i.value) for i in issues] == [("experiments links", "99")]
    assert issues[0].reason == "Experiment 99 does not exist"


def test_validate_row_flags_non_numeric_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_lookup(monkeypatch, {("resources", 3): 200})
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    issues = imp.validate_row(pd.Series({"resources links": "3; abc"}))
    assert len(issues) == 1
    assert issues[0].value == "abc"
    assert "not a valid Resource ID" in issues[0].reason


def test_validate_row_ignores_empty_and_unrelated_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_lookup(monkeypatch, {})
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    row = pd.Series({"experiments links": float("nan"), "Title": "nope", "Notes": "9"})
    assert imp.validate_row(row) == []
    assert calls == []


def test_validate_row_does_not_flag_when_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lookup(monkeypatch, {("experiments", 5): 500})
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    assert imp.validate_row(pd.Series({"experiments links": "5"})) == []


def test_validate_row_looks_each_id_up_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_lookup(monkeypatch, {("experiments", 5): 200})
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    for _ in range(3):
        imp.validate_row(pd.Series({"experiments links": "5"}))
    assert calls == [("experiments", 5)]


def test_validate_row_skipped_when_links_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_lookup(monkeypatch, {})
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    imp._SUPPORTS_LINKS = False
    assert imp.validate_row(pd.Series({"experiments links": "99"})) == []
    assert calls == []


# endregion


# region --- validate_row: extra fields, category, markers ---


def _meta(**fields: dict[str, Any]) -> dict[str, Any]:
    """Entity/template JSON carrying the given extra-field definitions."""
    return {"metadata": json.dumps({"extra_fields": fields})}


def _update_importer(entity_json: dict[str, Any]) -> DummyImporter:
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    imp._endpoint = FakeEndpoint(get=lambda **kw: FakeResponse(json_data=entity_json))
    return imp


def test_validate_row_flags_missing_link_in_extra_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lookup(monkeypatch, {("items", 7): 200})
    imp = _update_importer(_meta(GMO_Project={"type": "items", "value": ""}))
    ok = imp.validate_row(pd.Series({"gmo project": "7"}), entity_id="1")
    bad = imp.validate_row(pd.Series({"GMO_Project": "99"}), entity_id="1")
    junk = imp.validate_row(pd.Series({"GMO_Project": "abc"}), entity_id="1")
    assert ok == []
    assert [i.reason for i in bad] == ["Resource 99 does not exist (GMO_Project)"]
    assert "not a valid Resource ID" in junk[0].reason


def test_validate_row_flags_select_value_not_in_options() -> None:
    imp = _update_importer(_meta(Color={"type": "select", "options": ["Red", "Green"]}))
    assert imp.validate_row(pd.Series({"Color": "red"}), entity_id="1") == []
    issues = imp.validate_row(pd.Series({"Color": "Blue"}), entity_id="1")
    assert len(issues) == 1
    assert issues[0].column == "Color"
    assert issues[0].reason == (
        "'Blue' is not an option of 'Color' (options: Red, Green)"
    )


def test_validate_row_select_multi_value_rules() -> None:
    single = _update_importer(_meta(C={"type": "select", "options": ["a", "b"]}))
    # Single-select takes the first match, so one good value is enough.
    assert single.validate_row(pd.Series({"C": "a, zzz"}), entity_id="1") == []

    multi = _update_importer(
        _meta(C={"type": "select", "options": ["a", "b"], "allow_multi_values": True})
    )
    issues = multi.validate_row(pd.Series({"C": "a, zzz"}), entity_id="1")
    assert len(issues) == 1
    assert issues[0].value == "zzz"


def test_validate_row_ignores_fields_it_cannot_judge() -> None:
    imp = _update_importer(
        _meta(
            Empty={"type": "select", "options": []},
            Num={"type": "number"},
        )
    )
    row = pd.Series({"Empty": "anything", "Num": "not a number", "Unknown": "x"})
    assert imp.validate_row(row, entity_id="1") == []


def test_validate_row_leaves_update_markers_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_lookup(monkeypatch, {})
    imp = _update_importer(_meta(Color={"type": "select", "options": ["Red"]}))
    row = pd.Series(
        {
            "Color": "$delete_V",
            "experiments links": "$delete_V",
            "Other": "$rename$New Name",
        }
    )
    assert imp.validate_row(row, entity_id="1") == []
    assert calls == []


def test_validate_row_uses_template_fields_for_new_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[tuple[str, Any]] = []

    def fake_get_fixed(name: str) -> FakeEndpoint:
        def get(endpoint_id: Any, **_: Any) -> FakeResponse:
            requested.append((name, endpoint_id))
            return FakeResponse(
                json_data=_meta(Color={"type": "select", "options": ["Red"]})
            )

        return FakeEndpoint(get=get)

    monkeypatch.setattr("src.services.importers.base_importer.get_fixed", fake_get_fixed)
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    imp._TEMPLATE_ENDPOINT = "experiments_templates"

    for _ in range(3):
        issues = imp.validate_row(pd.Series({"Color": "Blue"}), template=12)
        assert len(issues) == 1
    # The template is fetched once, not once per row.
    assert requested == [("experiments_templates", "12")]


def test_validate_row_without_template_skips_field_checks() -> None:
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    imp._TEMPLATE_ENDPOINT = "experiments_templates"
    assert imp.validate_row(pd.Series({"Color": "Blue"})) == []


def test_validate_row_template_read_failure_skips_field_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.services.importers.base_importer.get_fixed",
        lambda name: FakeEndpoint(get=lambda **kw: FakeResponse(status_code=500)),
    )
    imp = DummyImporter(pd.DataFrame({"x": [1]}))
    imp._TEMPLATE_ENDPOINT = "experiments_templates"
    assert imp.validate_row(pd.Series({"Color": "Blue"}), template=3) == []


def test_validate_row_flags_non_numeric_category() -> None:
    imp = DummyImporter(pd.DataFrame({"Category ID": ["1"]}))
    issues = imp.validate_row(pd.Series({"Category ID": "Antibodies"}))
    assert [i.reason for i in issues] == ["'Antibodies' is not a valid category ID"]
    assert imp.validate_row(pd.Series({"Category ID": "12"})) == []
    # A column with blanks is read as floats: 12 arrives as 12.0.
    assert imp.validate_row(pd.Series({"Category ID": 12.0})) == []
    assert len(imp.validate_row(pd.Series({"Category ID": 12.5}))) == 1
    assert len(imp.validate_row(pd.Series({"Category ID": "-3"}))) == 1
    assert imp.validate_row(pd.Series({"Category ID": float("nan")})) == []


# endregion
