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

    # Subclasses must populate these at construction time.
    _KNOWN_POST_FIELDS: tuple[str, ...] = ()
    _template_id: int | str | None = None
    _default_category: str | None = None

    # Maps canonicalized CSV column headers to their elabFTW sub-endpoint names.
    _LINK_COLUMN_MAP: dict[str, str] = {
        canonicalize("experiments links"): "experiments_links",
        canonicalize("experiment link"): "experiments_links",
        canonicalize("resources link"): "items_links",
        canonicalize("resources links"): "items_links",
        canonicalize("items links"): "items_links",
    }

    # region --- Abstract interface ---

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

    # endregion

    # region --- Column utilities ---

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

    def _find_col_like(self, name: str) -> str | None:
        """Find a column whose canonical form matches or contains ``name``."""
        target = canonicalize(name)
        if target in self.cols_canon:
            return self.cols_canon[target]
        for canon_col, original in self.cols_canon.items():
            if target in canon_col or canon_col in target:
                return original
        return None

    def _find_path_col(self) -> str | None:
        """Find a column name that matches any known file path aliases."""
        path_aliases = {
            canonicalize(alias).replace("_", "") for alias in CONFIG["path_col"]
        }
        return next(
            (
                original
                for canon_col, original in self.cols_canon.items()
                if canon_col.replace("_", "") in path_aliases
            ),
            None,
        )

    def _find_entity_id_col(self, keyword: str) -> str | None:
        """Return the column name whose canonical form matches or contains ``keyword``."""
        for canon, original in self.cols_canon.items():
            c = canon.replace("_", "")
            if c == keyword or keyword in c:
                return original
        return None

    # endregion

    # region --- Value parsing ---

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

    def _parse_entity_id(
        self,
        id_col: str | None,
        row: pd.Series,
        row_index: int | None = None,
        entity_label: str = "Entity",
    ) -> str | None:
        """Extract and validate an entity id from a row; warn and skip on errors."""
        if id_col is None or id_col not in row:
            return None

        raw_id = row[id_col]
        eid = self.normalize_id(raw_id)
        label = f"row {row_index + 1}" if row_index is not None else "row ?"

        if eid is None:
            logger.warning(
                "Skipping %s: missing %s ID while update-existing is enabled.",
                label,
                entity_label,
            )
            return None

        eid_str = str(eid).split(".")[0].strip()
        if not eid_str.isdigit():
            logger.warning(
                "Skipping %s: invalid %s ID %r while update-existing is enabled.",
                label,
                entity_label,
                raw_id,
            )
            return None

        return eid_str

    @staticmethod
    def _split_multi(raw: str) -> list[str]:
        raw = raw.replace("\u00a0", " ")
        parts: list[str] = []
        for chunk in raw.replace(";", ",").split(","):
            s = chunk.strip()
            if s:
                parts.append(s)
        return parts

    @staticmethod
    def _parse_link_ids(raw: Any) -> list[int]:
        """Return a list of numeric link ids parsed from a CSV cell."""
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return []

        text = str(raw).replace("\u00a0", " ").strip()
        if not text:
            return []

        ids: list[int] = []
        for chunk in BaseImporter._split_multi(text):
            cleaned = chunk.strip()
            try:
                num = int(float(cleaned))
            except Exception:
                continue
            if num < 0:
                continue
            if num not in ids:
                ids.append(num)
        return ids

    @staticmethod
    def _coerce_for_field(defn: dict, raw: str) -> Any | None:
        ftype = (defn or {}).get("type")
        allow_multi = bool((defn or {}).get("allow_multi_values"))
        options = (defn or {}).get("options") or []
        options_set = {str(o).strip() for o in options}

        if ftype == "select":
            vals = BaseImporter._split_multi(raw)
            if allow_multi:
                lower_map = {o.lower(): o for o in options_set}
                picked: list[str] = []
                for v in vals:
                    if v in options_set and v not in picked:
                        picked.append(v)
                        continue
                    m = lower_map.get(v.lower())
                    if m and m not in picked:
                        picked.append(m)
                return picked
            else:
                for v in vals:
                    if v in options_set:
                        return v
                lower_map = {o.lower(): o for o in options_set}
                for v in vals:
                    m = lower_map.get(v.lower())
                    if m:
                        return m
                return None
        else:
            return raw

    # endregion

    # region --- Row field extraction ---

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

    def _get_tags(self, row: pd.Series) -> list[str]:
        """Parse tags column into list; supports sequences or delimited strings."""
        if row is None:
            return []
        tags_col = self.cols_canon.get("tags")
        if not tags_col or tags_col not in row:
            return []
        val = row[tags_col]
        if pd.isna(val):
            return []

        tags: list[str]

        if isinstance(val, (list, tuple, set)):
            tags = [str(x).strip() for x in val if str(x).strip()]
        elif isinstance(val, str):
            # detect delimiter
            for delim in [";", ",", "|"]:
                if delim in val:
                    parts = val.split(delim)
                    break
            else:
                parts = [val]
            tags = [p.strip() for p in parts if p.strip()]
        else:
            s = str(val).strip()
            if not s or s.lower() in {"nan", "none", "null"}:
                return []
            tags = [s]

        seen: set[str] = set()
        out: list[str] = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                out.append(tag)
        return out

    def _get_tags_str(self, row: pd.Series) -> str | None:
        return "|".join(self._get_tags(row))

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

    def get_category_id(self, row: pd.Series) -> str | None:
        """Return normalized numeric category id from row or None; raises on non-numeric."""
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

    def _collect_csv_extra_fields(
        self, row: pd.Series, known_columns: Iterable[str] | None = None
    ) -> dict[str, tuple[str, Any]]:
        known_canon = {canonicalize(x) for x in self._KNOWN_POST_FIELDS}
        if known_columns:
            known_canon |= {canonicalize(x) for x in known_columns}
        extras: dict[str, tuple[str, Any]] = {}
        for col, val in row.items():
            if not isinstance(col, str):
                continue
            ckey = canonicalize(col)
            if ckey in known_canon:
                continue
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            sval = str(val).replace("\u00a0", " ").strip()
            if not sval:
                continue
            extras[ckey] = (col, sval)
        return extras

    def _extract_known_post_fields(
        self, row: pd.Series, template: int | str | None
    ) -> dict[str, Any]:
        """Build POST payload from template and body."""
        data: dict[str, Any] = {}

        effective_template = (
            template
            if template is not None and str(template).strip()
            else self._template_id
        )
        if effective_template is not None:
            data["template"] = effective_template

        body_col = self._find_col_like("body")
        if body_col and body_col in row:
            body_val = row[body_col]
            if not pd.isna(body_val) and str(body_val).strip():
                data["body"] = str(body_val)

        return data

    # endregion

    # region --- ElabFTW reads ---

    def get_elab_id(self, response: Any) -> str:
        """Extract numeric id from a Location header; raise if missing/invalid."""
        headers: Mapping[str, str] | None = getattr(response, "headers", None)
        location = str(headers.get("Location", "")) if headers is not None else ""
        exp_id = location.rstrip("/").split("/")[-1]
        if not exp_id.isdigit():
            raise RuntimeError(f"Could not parse experiment ID: {exp_id!r}")
        return exp_id

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

    # endregion

    # region --- File uploads ---

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
            raise ValueError(f"Invalid elabFTW entry ID for upload: {entry_id!r}")

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

    def attach_single_file(self, entity_id: int | str, file: str | Path) -> None:
        """Upload a single file; prefer 'files[]' format, fallback to 'file'."""
        eid = str(entity_id)
        if not eid.isdigit():
            raise ValueError(f"Invalid entry ID for upload: {entity_id!r}")

        fp = Path(file)
        if not fp.exists() or not fp.is_file():
            raise FileNotFoundError(f"File not found or not a file: {fp}")

        mime = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"

        try:
            logger.debug("Uploading single file %s to entry %s", fp, eid)
            with fp.open("rb") as fh:
                resp = self.endpoint.post(
                    endpoint_id=eid,
                    sub_endpoint_name="uploads",
                    files=[("files[]", (fp.name, fh, mime))],
                )
            try:
                resp.raise_for_status()
                return
            except Exception:
                with fp.open("rb") as fh2:
                    resp2 = self.endpoint.post(
                        endpoint_id=eid,
                        sub_endpoint_name="uploads",
                        files={"file": (fp.name, fh2, mime)},
                    )
                resp2.raise_for_status()
        except Exception as exc:
            logger.error("Failed to upload file %s to entry %s: %s", fp, eid, exc)
            raise

    def attach_files(self, entity_id: int | str, path: str | Path) -> None:
        """Upload a file or every file in a directory recursively to an entry."""
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")

        if target.is_file():
            self.attach_single_file(entity_id, target)
            return

        files = self._iter_files_in_dir(target, recursive=True)
        if not files:
            logger.warning("No files to upload from: %s", target)
            return

        for fp in files:
            try:
                self.attach_single_file(entity_id, fp)
            except Exception as exc:
                logger.warning("Failed to upload %s to entry %s: %s", fp, entity_id, exc)

    # endregion

    # region --- ElabFTW writes ---

    @staticmethod
    def _normalize_tags(tags: list[str]) -> list[str]:
        """Strip, drop blanks, and de-duplicate a list of tags (order-preserving)."""
        normalized: list[str] = []
        seen: set[str] = set()
        for t in tags:
            if t is None:
                continue
            s = str(t).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            normalized.append(s)
        return normalized

    def replace_tags(self, resource_id: int | str, tags: list[str]) -> None:
        """Replace tags using the /{entity}/{id}/tags sub-endpoint."""
        rid = str(resource_id)
        if not rid.isdigit():
            raise ValueError(f"Invalid resource id: {resource_id!r}")

        normalized = self._normalize_tags(tags)
        if not normalized:
            return

        # Replace semantics: clear existing tags first.
        try:
            resp = self.endpoint.delete(endpoint_id=rid, sub_endpoint_name="tags")
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Could not clear existing tags for %s: %s", rid, exc)

        for tag in normalized:
            resp = self.endpoint.post(
                endpoint_id=rid,
                sub_endpoint_name="tags",
                data={"tag": tag},
            )
            resp.raise_for_status()

    def append_tags(
        self,
        resource_id: int | str,
        tags: list[str],
        existing_tags: str | None = None,
    ) -> None:
        """Add tags via the /{entity}/{id}/tags sub-endpoint, keeping existing ones.

        ``existing_tags`` is the pipe-separated tag string from the entity JSON;
        tags already present are skipped to avoid duplicates.
        """
        rid = str(resource_id)
        if not rid.isdigit():
            raise ValueError(f"Invalid resource id: {resource_id!r}")

        already_present: set[str] = set()
        if existing_tags:
            already_present = {
                t.strip() for t in str(existing_tags).split("|") if t.strip()
            }

        normalized = [
            t for t in self._normalize_tags(tags) if t not in already_present
        ]
        if not normalized:
            return

        for tag in normalized:
            resp = self.endpoint.post(
                endpoint_id=rid,
                sub_endpoint_name="tags",
                data={"tag": tag},
            )
            resp.raise_for_status()

    def _post_links(
        self, entity_id: str, link_ops: list[tuple[str, list[int]]]
    ) -> None:
        """Create links via sub-endpoints (experiments_links/items_links)."""
        for endpoint_name, ids in link_ops:
            sub_endpoint = endpoint_name
            for link_id in ids:
                try:
                    resp = self.endpoint.post(
                        endpoint_id=entity_id,
                        sub_endpoint_name=sub_endpoint,
                        sub_endpoint_id=link_id,
                    )
                    resp.raise_for_status()
                    logger.debug(
                        "Linked entry %s via %s -> %s",
                        entity_id,
                        sub_endpoint,
                        link_id,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to link entry %s via %s to %s: %s",
                        entity_id,
                        sub_endpoint,
                        link_id,
                        exc,
                    )

    def patch_decoded_extra_fields(
        self, elab_id: str, row: pd.Series, known_columns: Iterable[str]
    ) -> None:
        """Patch extra fields using the metadata_decoded (list) format, skipping known columns."""
        existing = self.get_existing_json(elab_id)
        if not existing:
            return
        extra_map = self.fetch_extra_fields_mapping(existing)
        if not extra_map:
            return
        known_canon = {canonicalize(column) for column in known_columns}
        updated_fields: list[str] = []
        for column in row.index:
            canon_col = canonicalize(column)
            if canon_col in extra_map and canon_col not in known_canon:
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

    def post_extra_fields_from_row(
        self,
        entity_id: int | str,
        row: pd.Series,
        known_columns: Iterable[str] | None = None,
        delete_value_columns: Iterable[str] | None = None,
        delete_field_columns: Iterable[str] | None = None,
    ) -> None:
        """Match CSV extras to template fields, coerce, and patch metadata JSON."""
        eid = str(entity_id)
        existing_json = self.get_existing_json(eid)

        raw_metadata = existing_json.get("metadata") or {}

        if isinstance(raw_metadata, str):
            try:
                metadata = json.loads(raw_metadata)
            except Exception:
                metadata = {}
        else:
            metadata = raw_metadata

        elab_extra_fields: dict[str, dict] = metadata.setdefault("extra_fields", {})

        defs_by_canon: dict[str, str] = {}
        for orig_key in list(elab_extra_fields.keys()):
            c = canonicalize(orig_key)
            if c not in defs_by_canon:
                defs_by_canon[c] = orig_key

        known_canon = {canonicalize(x) for x in self._KNOWN_POST_FIELDS}
        if known_columns:
            known_canon |= {canonicalize(x) for x in known_columns}

        def marker_keys(columns: Iterable[str] | None) -> set[str]:
            return {
                canonicalize(column)
                for column in columns or []
                if isinstance(column, str) and canonicalize(column) not in known_canon
            }

        delete_value_keys = marker_keys(delete_value_columns)
        delete_field_keys = marker_keys(delete_field_columns)
        marker_handled_keys = delete_value_keys | delete_field_keys

        csv_extras = self._collect_csv_extra_fields(row, known_columns=known_columns)

        changed: dict[str, Any] = {}
        link_ops: list[tuple[str, list[int]]] = []

        for ckey in delete_field_keys:
            real_key = defs_by_canon.get(ckey)
            if real_key is None:
                continue
            del elab_extra_fields[real_key]
            changed[real_key] = None

        for ckey in delete_value_keys - delete_field_keys:
            real_key = defs_by_canon.get(ckey)
            if real_key is None:
                continue
            slot = elab_extra_fields.get(real_key)
            if not isinstance(slot, dict):
                elab_extra_fields[real_key] = {"value": ""}
            else:
                slot["value"] = ""
            changed[real_key] = ""

        for ckey in marker_handled_keys:
            csv_extras.pop(ckey, None)

        for ckey, (orig_col, raw_val) in list(csv_extras.items()):
            if ckey not in self._LINK_COLUMN_MAP:
                continue

            target_key = self._LINK_COLUMN_MAP[ckey]
            link_ids = self._parse_link_ids(raw_val)
            if not link_ids:
                continue

            del csv_extras[ckey]
            link_ops.append((target_key, link_ids))

        for ckey, (orig_col, raw_val) in csv_extras.items():
            if ckey in defs_by_canon:
                real_key = defs_by_canon[ckey]
                defn = elab_extra_fields.get(real_key) or {}
                coerced = self._coerce_for_field(defn, raw_val)

                if coerced is None:
                    logger.info(
                        "Skipping field %r: value %r not valid for options.",
                        real_key,
                        raw_val,
                    )
                    continue
                slot = elab_extra_fields.get(real_key)

                if not isinstance(slot, dict):
                    elab_extra_fields[real_key] = {"value": coerced}
                else:
                    slot["value"] = coerced
                changed[real_key] = coerced
                continue

            new_key = orig_col
            elab_extra_fields[new_key] = {"value": raw_val}
            changed[new_key] = raw_val

        self._post_links(eid, link_ops)

        if not changed:
            if link_ops:
                logger.info(
                    "Only links to create for entry %s; skipping metadata patch.", eid
                )
            else:
                logger.info("No matching extra fields to upload for entry %s.", eid)
            return

        logger.debug(
            "Patching extra fields for entry %s: %s", eid, list(changed.keys())
        )

        metadata_str = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        payload = {"metadata": metadata_str}

        resp = self.endpoint.patch(endpoint_id=eid, data=payload)

        try:
            resp.raise_for_status()
        except Exception as exc:
            logger.error(
                "Failed to patch extra fields for entry %s: %s %s | payload keys=%s",
                eid,
                getattr(resp, "status_code", "?"),
                getattr(resp, "text", ""),
                list(payload.keys()),
            )
            raise RuntimeError(
                f"Failed to patch extra fields for entry {eid}: "
                f"{getattr(resp, 'status_code', '?')} {getattr(resp, 'text', '')}"
            ) from exc

    # endregion

    # region --- Entry creation ---

    def _increment_new_counter(self) -> None:
        """Increment the new-entry counter. Override in subclasses."""

    def create_new(self, row: pd.Series, template: int | str | None = None) -> str:
        payload = self._extract_known_post_fields(row, template)
        logger.debug("Creating entry with payload fields: %s", list(payload.keys()))
        response = self.endpoint.post(data=payload)

        try:
            response.raise_for_status()
        except Exception as exc:
            title = payload.get("title", "<unknown title>")
            raise RuntimeError(
                f"Creation of {title!r} failed with status "
                f"{response.status_code}: {response.text}"
            ) from exc

        entity_id = str(self.get_elab_id(response))
        logger.info("Created entry %s", entity_id)

        category_id = self.get_category_id(row) or self._default_category
        if category_id:
            patch_resp = None
            try:
                patch_resp = self.endpoint.patch(
                    endpoint_id=entity_id, data={"category": category_id}
                )
                patch_resp.raise_for_status()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to patch category for entry {entity_id}: "
                    f"{getattr(patch_resp, 'status_code', '?')} "
                    f"{getattr(patch_resp, 'text', '')}"
                ) from exc

        tags_list = self._get_tags(row)
        if tags_list:
            self.replace_tags(entity_id, tags_list)

        if title := self._get_title(row):
            patch_resp = None
            try:
                patch_resp = self.endpoint.patch(
                    endpoint_id=entity_id, data={"title": title}
                )
                patch_resp.raise_for_status()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to patch title for entry {entity_id}: "
                    f"{getattr(patch_resp, 'status_code', '?')} "
                    f"{getattr(patch_resp, 'text', '')}"
                ) from exc

        path_col = self._find_path_col()
        if path_col and path_col in row:
            folder_path = self._resolve_folder(row[path_col])

            if folder_path and folder_path.exists():
                self.attach_files(entity_id, folder_path)
            elif folder_path:
                logger.warning("Files path does not exist: %s", folder_path)

        known = {canonicalize(name) for name in self._KNOWN_POST_FIELDS}
        if path_col:
            known.add(canonicalize(path_col))
        self.post_extra_fields_from_row(entity_id, row, known_columns=known)

        self._increment_new_counter()
        return entity_id

    def create_all_from_csv(self, template: int | str | None = None) -> list[str]:
        """Create all items from the loaded CSV. Subclasses should override."""
        raise NotImplementedError(
            "create_all_from_csv must be implemented by importer subclasses"
        )

    # endregion
