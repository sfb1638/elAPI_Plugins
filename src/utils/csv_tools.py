import csv
from io import StringIO
from pathlib import Path

import chardet
import pandas as pd


class CsvTools:
    @staticmethod
    def detect_file_encoding(path: Path | str, read_bytes: int = 100_000) -> str:
        with open(path, "rb") as f:
            raw = f.read(read_bytes)
        result = chardet.detect(raw)
        return result.get("encoding") or "utf-8"

    @staticmethod
    def _normalize_text(text: str) -> str:
        return (
            text.replace("\ufeff", "")  # BOM
            .replace("\u00a0", " ")  # NBSP -> space
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

    @staticmethod
    def detect_delimiter(path: Path | str, encoding: str) -> str:
        with open(path, encoding=encoding, errors="ignore") as f:
            sample = f.read(8192)  # larger sample helps sniffing
        sample = CsvTools._normalize_text(sample)

        try:
            sniff = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return sniff.delimiter
        except csv.Error:
            # Heuristic fallback: inspect the first non-empty line (likely the header)
            header = next((ln for ln in sample.splitlines() if ln.strip()), "")
            candidates = [";", "\t", "|", ","]
            counts = {d: header.count(d) for d in candidates}
            best = max(counts, key=lambda delim: counts[delim])
            # Require at least two occurrences; otherwise default to semicolon
            return best if counts[best] >= 2 else ";"

    @staticmethod
    def csv_to_df(csv_path: Path | str) -> pd.DataFrame:
        enc = CsvTools.detect_file_encoding(path=csv_path)
        delimiter = CsvTools.detect_delimiter(path=csv_path, encoding=enc)

        with open(csv_path, encoding=enc, errors="ignore") as f:
            raw = f.read()
        raw = CsvTools._normalize_text(raw)

        df = pd.read_csv(
            StringIO(raw),
            sep=delimiter,
            engine="python",
        )
        return df
