import csv
import logging
from io import StringIO
from pathlib import Path

import chardet
import pandas as pd

logger = logging.getLogger(__name__)


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
        with open(path, encoding=encoding, errors="replace") as f:
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
            delimiter = best if counts[best] >= 2 else ";"
            logger.debug(
                "csv.Sniffer could not detect a delimiter for %s; "
                "falling back to %r (header counts: %s).",
                path,
                delimiter,
                counts,
            )
            return delimiter

    @staticmethod
    def _decode_file(path: Path | str) -> tuple[str, str]:
        """Return ``(text, encoding)`` for the whole file.

        UTF-8 is tried on the full content first: sampling only the start of a
        file can look like ASCII and miss non-ASCII characters further down.
        Only when that fails is the encoding guessed, from the full content.
        """
        with open(path, "rb") as f:
            data = f.read()
        try:
            return data.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
        enc = chardet.detect(data).get("encoding") or "cp1252"
        # Never drop characters silently; replacement marks show up in the data.
        text = data.decode(enc, errors="replace")
        if "\ufffd" in text:
            logger.warning("%s: some characters could not be decoded as %s.", path, enc)
        return text, enc

    @staticmethod
    def csv_to_df(csv_path: Path | str) -> pd.DataFrame:
        raw, enc = CsvTools._decode_file(csv_path)
        delimiter = CsvTools.detect_delimiter(path=csv_path, encoding=enc)
        raw = CsvTools._normalize_text(raw)

        df = pd.read_csv(
            StringIO(raw),
            sep=delimiter,
            engine="python",
        )
        return df

    @staticmethod
    def detect_field_rename(columns: pd.Index) -> dict[str, str]:
        """Parse 'CSV Name->ELab Name' headers and return a {old: new} rename dict."""
        return{
            col: col.split("->", 1)[1].strip()
            for col in columns
            if "->" in col
        }
