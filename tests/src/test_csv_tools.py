from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.csv_tools import CsvTools


def test_detect_delimiter_prefers_semicolon(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("col1;col2;col3\n1;2;3\n", encoding="utf-8")
    delim = CsvTools.detect_delimiter(csv_path, encoding="utf-8")
    assert delim == ";"


def test_csv_to_df_handles_bom_and_newlines(tmp_path: Path) -> None:
    # Include BOM and Windows newlines to exercise normalization
    csv_path = tmp_path / "bom.csv"
    csv_path.write_bytes("\ufeffa,b\r\n1,2\r\n".encode())

    df = CsvTools.csv_to_df(csv_path)

    assert list(df.columns) == ["a", "b"]
    assert df.iloc[0].tolist() == [1, 2]
    assert isinstance(df, pd.DataFrame)


def test_detect_file_encoding_returns_utf8(tmp_path: Path) -> None:
    csv_path = tmp_path / "enc.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    enc = CsvTools.detect_file_encoding(csv_path)
    assert enc.lower().replace("-", "") in {"utf8", "utf", "ascii"}  # allow alias


def test_csv_to_df_keeps_non_ascii_after_ascii_prefix(tmp_path: Path) -> None:
    csv_path = tmp_path / "late.csv"
    body = "title;note\n" + "a;b\n" * 30000 + "Müller;Größe\n"
    csv_path.write_bytes(body.encode("utf-8"))

    df = CsvTools.csv_to_df(csv_path)

    assert df.iloc[-1].tolist() == ["Müller", "Größe"]


def test_csv_to_df_falls_back_to_legacy_encoding(tmp_path: Path) -> None:
    csv_path = tmp_path / "latin.csv"
    csv_path.write_bytes("title;note\nMüller;Größe\n".encode("cp1252"))

    df = CsvTools.csv_to_df(csv_path)

    assert df.iloc[0].tolist() == ["Müller", "Größe"]
