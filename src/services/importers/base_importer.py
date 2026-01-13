"""Base importer utilities for ElabFTW resources/experiments."""

from __future__ import annotations

import json
import logging
import math
import mimetypes
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from elapi.api import FixedEndpoint

from src.utils.common import canonicalize, ensure_series
from src.utils.paths import RES_IMPORTER_CONFIG

try:
    with open(RES_IMPORTER_CONFIG, encoding="utf-8") as config_file:
        CONFIG = json.load(config_file)
except FileNotFoundError:
    raise FileNotFoundError(
        f"Config file not found. Tried: {RES_IMPORTER_CONFIG}. "
        "Set RES_IMPORTER_CONFIG to override, or ensure "
        "config/res_importer_config.json exists at repo root."
    ) from None
except json.JSONDecodeError as exc:
    raise ValueError(f"Error decoding JSON from {RES_IMPORTER_CONFIG}: {exc}") from exc

logger = logging.getLogger(__name__)


class BaseImporter(ABC):
    """Shared helpers for importer subclasses (ids, columns, tags, files, extras)."""

    def _canonicalize_column_indexes(self, columns: pd.Index) -> dict[str, str]:
        canon_column_map: dict[str, str] = {}

        for original_name in columns:
            if not isinstance(original_name, str):
                continue

            canon_lower_key = canonicalize(original_name.lower())

            if canon_lower_key in canon_column_map and canon_lower_key != original_name:
                logger.debug(
                    "Canonicalized lowercase column collision: %r vs %r for key %r",
                    canon_column_map[canon_lower_key],
                    original_name,
                    canon_lower_key,
                )
            else:
                canon_column_map.setdefault(canon_lower_key, original_name)

        return canon_column_map

    def _find_path_col(self) -> str | None:
        """Find a column name that matches any known file path aliases."""
        return next(
            (col for col in self.cols_canon.values() if col in CONFIG["path_col"]), None
        )

    def _normalize_date(self, row: pd.Series | Any) -> str | None:
        row_series = ensure_series(row)
        if row_series is None:
            return None

        date_col = self.cols_canon.get("date")

        if date_col is None or date_col not in row_series.index:
            return None

        date_val = row_series[date_col]

        if pd.isna(date_val):
            return None

        date_str = str(date_val).strip()
        if not date_str:
            return None

        for pattern in CONFIG["date_patterns"]:
            try:
                dt = datetime.strptime(date_str, pattern)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        logger.warning("Unrecognized date format: %r", date_str)
        return None

    @property
    @abstractmethod
    def basic_df(self) -> pd.DataFrame:
        """Return the DataFrame backing the importer."""
        raise NotImplementedError

    @property
    @abstractmethod
    def cols_canon(self) -> dict[str, str]:
        """Map canonicalized column names to their originals."""
        raise NotImplementedError

    @property
    @abstractmethod
    def endpoint(self) -> FixedEndpoint:
        """Return the endpoint used to interact with ElabFTW."""
        raise NotImplementedError

    @property
    def files_base_dir(self) -> Path | None:
        """Optional base directory for resolving relative file paths."""
        return None

    @property
    def df(self) -> pd.DataFrame:
        """Alias for the backing DataFrame used by some importers."""
        return self.basic_df

    def _find_col_like(self, name: str) -> str | None:
        """Find a column whose canonical form matches or contains ``name``."""
        target = canonicalize(name)
        if target in self.cols_canon:
            return self.cols_canon[target]
        for canon_col, original in self.cols_canon.items():
            if target in canon_col or canon_col in target:
                return original
        return None

    def _iter_files_in_dir(
        self, folder: str | Path, recursive: bool = True
    ) -> list[Path]:
        path = Path(str(folder)).expanduser()

        if not path.exists() or not path.is_dir():
            logger.warning("Files folder does not exist or is not a directory: %s", path)
            return []

        if recursive:
            files = [f for f in path.rglob("*") if f.is_file()]
        else:
            files = [f for f in path.iterdir() if f.is_file()]

        if not files:
            logger.warning("No files found in folder: %s", path)

        return files

    def _resolve_folder(self, raw_value: str | Path) -> Path | None:
        """Convert a CSV cell to Path when it plausibly represents a file/folder."""
        if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
            return None

        # Convert to string, normalize whitespace and non-breaking spaces
        path_str = str(raw_value).replace("\u00a0", " ").strip()
        if not path_str:
            return None

        looks_like_path = (
            any(ch in path_str for ch in (os.sep, "/", "\\"))
            or os.path.isabs(path_str)
            or "." in os.path.basename(path_str)
            or self.files_base_dir is not None
        )

        if not looks_like_path:
            logger.info(
                "Skipping files upload: value does not look like a path: %r", path_str
            )
            return None

        resolved_path = Path(path_str).expanduser()

        if not resolved_path.is_absolute() and self.files_base_dir:
            resolved_path = (self.files_base_dir / resolved_path).resolve()

        return resolved_path

    def _attach_files(
        self,
        entry_id: int | str,
        folder: str | Path,
        recursive: bool = True,
        chunk_size: int = 10,
    ) -> None:
        entry_id = str(entry_id)

        if not entry_id.isdigit():
            raise ValueError(f"Invalid elabFTW entry ID for upload:"
                             f" {entry_id!r}")

        logger.info("Uploading files for elabFTW entry ID %s from %s", entry_id, folder)
        files = self._iter_files_in_dir(folder, recursive=recursive)
        if not files:
            logger.warning("No files to upload from: %s", folder)
            return

        def _mime_or_default(p: Path) -> str:
            return mimetypes.guess_type(p.name)[0] or "application/octet-stream"

        def _send_batch(batch: list[Path]) -> bool:
            payload = []
            handles = []
            try:
                for fp in batch:
                    fh = fp.open("rb")
                    handles.append(fh)
                    payload.append(("files[]", (fp.name, fh, _mime_or_default(fp))))
                try:
                    resp = self.endpoint.post(
                        endpoint_id=entry_id, sub_endpoint_name="uploads", files=payload
                    )
                    resp.raise_for_status()
                    logger.debug(
                        "Uploaded batch of %d files for resource %s", len(batch), entry_id
                    )
                    return True
                except Exception as exc:
                    logger.info("Batched upload (%d files) failed: %s", len(batch), exc)
                    return False
            finally:
                for h in handles:
                    try:
                        h.close()
                    except Exception:
                        pass

        if chunk_size and chunk_size > 1:
            i = 0
            all_batches_ok = True
            while i < len(files):
                batch = files[i : i + chunk_size]
                ok = _send_batch(batch)
                if not ok:
                    all_batches_ok = False
                    break
                i += chunk_size
            if all_batches_ok:
                logger.info(
                    "Uploaded %d files in %d batch(es).",
                    len(files),
                    (len(files) + chunk_size - 1) // chunk_size,
                )
                return

        errors: list[str] = []
        for fp in files:
            try:
                logger.debug("Uploading file %s to resource %s", fp, entry_id)
                with fp.open("rb") as fh:
                    resp = self.endpoint.post(
                        endpoint_id=entry_id,
                        sub_endpoint_name="uploads",
                        files=[("files[]", (fp.name, fh, _mime_or_default(fp)))],
                    )
                try:
                    resp.raise_for_status()
                    continue
                except Exception:
                    with fp.open("rb") as fh2:
                        resp2 = self.endpoint.post(
                            endpoint_id=entry_id,
                            sub_endpoint_name="uploads",
                            files={"file": (fp.name, fh2, _mime_or_default(fp))},
                        )
                    resp2.raise_for_status()
            except Exception as exc:
                logger.error(
                    "Failed to upload file %s to resource %s: %s", fp, entry_id, exc
                )
                errors.append(f"{fp}: {exc}")

        if errors:
            raise RuntimeError("One or more uploads failed:\n- " + "\n- ".join(errors))

    def validate_category_id(self, cid: str) -> None:
        """Validate that a category ID is numeric."""

        if not str(cid).isdigit():
            raise ValueError("Category ID must be numeric.")

    def resolve_category_col(self) -> str | None:
        """Try to identify the column storing category ids from the DataFrame."""

        for c in self.basic_df.columns:
            canon = canonicalize(c)
            if (
                canon.startswith("categoryid")
                or "categoryid" in canon
                or canon == "category"
                or canon == "cat"
            ):
                return c
        return None

    def normalize_id(self, value: Any) -> str | None:
        """Return a normalised identifier or ``None`` if the value is empty."""
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        s = str(value).strip()
        if s.lower() in {"", "nan", "none", "null"}:
            return None
        return s

    def get_category_id(self, row: pd.Series) -> str | None:
        """Return normalized numeric category id from row or None; raises on non-numeric."""  # noqa: E501
        if row is None or not isinstance(row, pd.Series):
            return None
        col = self.resolve_category_col()
        if col is None or col not in row:
            return None
        cid = self.normalize_id(row[col])
        if cid is None:
            return None
        self.validate_category_id(cid)
        return cid

    def get_elab_id(self, response: Any) -> str:
        """Extract numeric id from a Location header; raise if missing/invalid."""
        headers: Mapping[str, str] | None = getattr(response, "headers", None)
        location = str(headers.get("Location", "")) if headers is not None else ""
        exp_id = location.rstrip("/").split("/")[-1]
        if not exp_id.isdigit():
            raise RuntimeError(f"Could not parse experiment ID: {exp_id!r}")
        return exp_id

    def _get_title(self, row: pd.Series) -> str | None:
        """Return the title value from a row."""

        if row is None:
            return None
        if not isinstance(row, pd.Series):
            try:
                row = pd.Series(row._asdict())
            except Exception:
                return None

        title_col = self.cols_canon.get("title")

        if not title_col or title_col not in row:
            return None

        title_val = row[title_col]

        if title_val is None or str(title_val).strip() == "":
            return None

        return str(title_val).strip()

    def get_tags(self, row: pd.Series) -> list[str]:
        """Parse tags column into list; supports sequences or delimited strings."""
        if row is None:
            return []
        tags_col = self.cols_canon.get("tags")
        if not tags_col or tags_col not in row:
            return []
        val = row[tags_col]
        if pd.isna(val):
            return []
        if isinstance(val, (list, tuple, set)):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str):
            for delim in [";", ",", "|"]:
                if delim in val:
                    parts = val.split(delim)
                    break
            else:
                parts = [val]
            return [p.strip() for p in parts if p.strip()]
        s = str(val).strip()
        if not s or s.lower() in {"nan", "none", "null"}:
            return []
        return [s]

    def get_existing_json(self, elab_id: str) -> dict[str, Any]:
        """Fetch existing record JSON for id; return empty dict on failure."""
        try:
            logger.debug("Fetching existing JSON for id %s", elab_id)
            response = self.endpoint.get(endpoint_id=elab_id)
            response_json = response.json()
            if isinstance(response_json, dict):
                return response_json
        except Exception as exc:
            logger.warning("Failed to fetch existing JSON for id %s: %s", elab_id, exc)
        return {}

    def fetch_extra_fields_mapping(
        self, elab_json: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Map canonicalized extra field titles to their definitions."""
        metadata_decoded = elab_json.get("metadata_decoded", {})
        extra_fields = metadata_decoded.get("extra_fields", [])
        mapping: dict[str, dict[str, Any]] = {}
        if isinstance(extra_fields, list):
            for field in extra_fields:
                if not isinstance(field, dict):
                    continue
                title = field.get("title") or field.get("slug") or field.get("name")
                if title:
                    mapping[canonicalize(title)] = field
        return mapping

    def update_extra_fields_from_row(
        self, elab_id: str, row: pd.Series, known_columns: Iterable[str]
    ) -> None:
        """Patch existing extra fields with CSV values, skipping known columns."""
        existing = self.get_existing_json(elab_id)
        if not existing:
            return
        extra_map = self.fetch_extra_fields_mapping(existing)
        if not extra_map:
            return
        updated_fields: list[str] = []
        for column in row.index:
            canon_col = canonicalize(column)
            if canon_col in extra_map and canon_col not in known_columns:
                value = row[column]
                if pd.isna(value):
                    val_str = ""
                else:
                    if hasattr(value, "item") and not isinstance(value, str):
                        try:
                            value = value.item()
                        except Exception:
                            pass
                    val_str = str(value)
                extra_map[canon_col]["value"] = val_str
                updated_fields.append(canon_col)
        patch_data = {"metadata": {"extra_fields": list(extra_map.values())}}
        try:
            logger.debug("Patching extra fields for id %s: %s", elab_id, updated_fields)
            response = self.endpoint.patch(endpoint_id=elab_id, data=patch_data)
            response.raise_for_status()
        except Exception as exc:
            logger.error("Failed to patch extra fields for id %s: %s", elab_id, exc)

    def create_all_from_csv(self, template: int | str | None = None) -> list[str]:
        """Create all items from the loaded CSV. Subclasses should override."""
        raise NotImplementedError(
            "create_all_from_csv must be implemented by importer subclasses"
        )
