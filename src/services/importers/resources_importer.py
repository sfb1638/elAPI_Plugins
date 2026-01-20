from __future__ import annotations

import json
import logging
import mimetypes
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import elapi.api
import pandas as pd

from src.utils.common import canonicalize as canonicalize_field
from src.utils.csv_tools import CsvTools
from src.utils.endpoints import get_fixed
from src.utils.logging_config import setup_logging
from src.utils.paths import RES_IMPORTER_CONFIG

from .base_importer import BaseImporter

logger = logging.getLogger(__name__)

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


class ResourcesImporter(BaseImporter):
    """Importer for the ElabFTW ``resources`` endpoint."""

    _KNOWN_POST_FIELDS: set[str] = set(CONFIG["known_post_fields"])
    _LINK_COLUMN_MAP: dict[str, str] = {
        # CSV column (canonicalized) -> payload field name returned by API
        canonicalize_field("experiments links"): "experiments_links",
        canonicalize_field("experiment link"): "experiments_links",
        canonicalize_field("resources link"): "items_links",
        canonicalize_field("resources links"): "items_links",
        canonicalize_field("items links"): "items_links",
    }

    def __init__(
        self,
        csv_path: Path | str,
        files_base_dir: str | Path | None = None,
        template_id: int | str | None = None,
        category_id: int | str | None = None,
    ) -> None:
        setup_logging()
        self._endpoint: elapi.api.FixedEndpoint = get_fixed("resources")
        self._resources_df: pd.DataFrame = CsvTools.csv_to_df(csv_path)
        self._cols_canon: dict[str, str] = self._canonicalize_column_indexes(
            self._resources_df.columns
        )
        self._template_id: int | str | None = template_id
        self._category_col: str | None = self.resolve_category_col()
        self._files_base_dir: Path | None = (
            Path(files_base_dir).expanduser() if files_base_dir else None
        )
        self._new_resources_counter: int = 0
        self._patched_resources_counter: int = 0
        self._default_category: str | None = self.normalize_id(category_id)
        if self._default_category is not None:
            self.validate_category_id(self._default_category)
        logger.info("Loaded resources   CSV with %d rows",
                    len(self._resources_df))
    @property
    def basic_df(self) -> pd.DataFrame:
        return self._resources_df

    @property
    def cols_canon(self) -> dict[str, str]:
        return self._cols_canon

    @property
    def endpoint(self) -> elapi.api.FixedEndpoint:
        return self._endpoint

    @property
    def files_base_dir(self) -> Path | None:
        return self._files_base_dir

    def attach_single_file(self, resource_id: int | str, file: str | Path) -> None:
        """Upload a single file; prefer 'files[]', fallback to 'file'."""
        rid = str(resource_id)
        if not rid.isdigit():
            raise ValueError(f"Invalid resource ID for upload: {resource_id!r}")

        fp = Path(file)
        if not fp.exists() or not fp.is_file():
            raise FileNotFoundError(f"File not found or not a file: {fp}")

        mime = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"

        try:
            logger.debug("Uploading single file %s to resource %s", fp, rid)
            with fp.open("rb") as fh:
                resp = self.endpoint.post(
                    endpoint_id=rid,
                    sub_endpoint_name="uploads",
                    files=[("files[]", (fp.name, fh, mime))],
                )
            try:
                resp.raise_for_status()
                return
            except Exception:
                with fp.open("rb") as fh2:
                    resp2 = self.endpoint.post(
                        endpoint_id=rid,
                        sub_endpoint_name="uploads",
                        files={"file": (fp.name, fh2, mime)},
                    )
                resp2.raise_for_status()
        except Exception as exc:
            logger.error("Failed to upload file %s to resource %s: %s", fp, rid, exc)
            raise

    def attach_files(self, resource_id: int | str, folder: str | Path) -> None:
        chunk_size = CONFIG.get("upload_chunk_size", 10)
        self._attach_files(resource_id, folder, recursive=True, chunk_size=chunk_size)

    def _collect_csv_extra_fields(
        self, row: pd.Series, known_columns: Iterable[str] | None = None
    ) -> dict[str, tuple[str, Any]]:
        known_canon = {canonicalize_field(x) for x in self._KNOWN_POST_FIELDS}
        if known_columns:
            known_canon |= {canonicalize_field(x) for x in known_columns}
        extras: dict[str, tuple[str, Any]] = {}
        # Collects non‑null, non‑standard fields from row
        for col, val in row.items():
            if not isinstance(col, str):
                continue
            ckey = canonicalize_field(col)
            if ckey in known_canon:
                continue
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            sval = str(val).replace("\u00a0", " ").strip()
            if not sval:
                continue
            extras[ckey] = (col, sval)
        return extras

    @staticmethod
    def _parse_link_ids(raw: Any) -> list[int]:
        """Return a list of numeric link ids parsed from a CSV cell."""
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return []

        text = str(raw).replace("\u00a0", " ").strip()
        if not text:
            return []

        ids: list[int] = []
        for chunk in ResourcesImporter._split_multi(text):
            # Allow numbers that may have been read as floats like '123.0'
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

    def _post_links(self, resource_id: str, link_ops: list[tuple[str, list[int]]]) -> None:
        """Create links via sub-endpoints (experiments_links/items_links)."""
        for endpoint_name, ids in link_ops:
            sub_endpoint = endpoint_name
            for link_id in ids:
                try:
                    resp = self.endpoint.post(
                        endpoint_id=resource_id,
                        sub_endpoint_name=sub_endpoint,
                        sub_endpoint_id=link_id,
                    )
                    resp.raise_for_status()
                    logger.debug(
                        "Linked resource %s via %s -> %s", resource_id, sub_endpoint, link_id
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to link resource %s via %s to %s: %s",
                        resource_id,
                        sub_endpoint,
                        link_id,
                        exc,
                    )

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
    def _coerce_for_field(defn: dict, raw: str) -> Any | None:
        ftype = (defn or {}).get("type")
        allow_multi = bool((defn or {}).get("allow_multi_values"))
        options = (defn or {}).get("options") or []
        options_set = {str(o).strip() for o in options}

        if ftype == "select":
            vals = ResourcesImporter._split_multi(raw)
            # Coerces single or multiple select values
            if allow_multi:
                lower_map = {o.lower(): o for o in options_set}
                picked: list[str] = []
                # Accumulates case‑sensitive and insensitive matches from options
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

    def post_extra_fields_from_row(
        self,
        resource_id: int | str,
        row: pd.Series,
        known_columns: Iterable[str] | None = None,
    ) -> None:
        """Match CSV extras to template fields, coerce, and patch metadata JSON."""
        rid = str(resource_id)
        existing_json = self.get_existing_json(rid)

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
            c = canonicalize_field(orig_key)
            if c not in defs_by_canon:
                defs_by_canon[c] = orig_key

        csv_extras = self._collect_csv_extra_fields(row, known_columns=known_columns)

        changed: dict[str, Any] = {}

        link_ops: list[tuple[str, list[int]]] = []

        # Handle link columns that should target specific API link sub-endpoints
        for ckey, (orig_col, raw_val) in list(csv_extras.items()):
            if ckey not in self._LINK_COLUMN_MAP:
                continue

            target_key = self._LINK_COLUMN_MAP[ckey]
            link_ids = self._parse_link_ids(raw_val)
            if not link_ids:
                # leave as normal extra if no numeric ids were found
                continue

            del csv_extras[ckey]  # avoid double-handling as generic extra
            link_ops.append((target_key, link_ids))

        for ckey, (orig_col, raw_val) in csv_extras.items():
            # Updates resource with coerced value when definition exists
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

            # Create a new extra field when no matching definition exists on the resource
            new_key = orig_col
            elab_extra_fields[new_key] = {"value": raw_val}
            changed[new_key] = raw_val

        # Create links through dedicated sub-endpoints
        self._post_links(rid, link_ops)

        if not changed:
            if link_ops:
                logger.info("Only links to create for resource %s; skipping metadata patch.", rid)
            else:
                logger.info("No matching extra fields to upload for resource %s.", rid)
            return

        logger.debug(
            "Patching extra fields for resource %s: %s", rid, list(changed.keys())
        )

        metadata_str = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        payload = {"metadata": metadata_str}

        if not payload:
            logger.info("No extra fields changed for resource %s.", rid)
            return

        resp = self.endpoint.patch(endpoint_id=rid, data=payload)

        try:
            resp.raise_for_status()
        except Exception as exc:
            # Log server feedback to help debug invalid payloads (e.g., link fields)
            logger.error(
                "Failed to patch extra fields for resource %s: %s %s | payload keys=%s",
                rid,
                getattr(resp, "status_code", "?"),
                getattr(resp, "text", ""),
                list(payload.keys()),
            )
            raise RuntimeError(
                f"Failed to patch extra fields for resource {rid}: "
                f"{getattr(resp, 'status_code', '?')} {getattr(resp, 'text', '')}"
            ) from exc

    def _extract_known_post_fields(
        self, row: pd.Series, template: int | str | None
    ) -> dict[str, Any]:
        """Build POST payload from title, tags, category, body, template."""

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

    def create_new(self, row: pd.Series, template: int | str | None = None) -> str:
        payload = self._extract_known_post_fields(row, template)
        logger.debug("Creating resource with payload fields: %s", list(payload.keys()))
        response = self.endpoint.post(data=payload)

        try:
            response.raise_for_status()
        except Exception as exc:
            title = payload.get("title", "<unknown title>")
            raise RuntimeError(
                f"Creation of {title!r} failed with status "
                f"{response.status_code}: {response.text}"
            ) from exc

        resource_id = str(self.get_elab_id(response))
        logger.info("Created resource %s", resource_id)
        category_id = self.get_category_id(row) or self._default_category
        if category_id:
            patch_resp = None
            try:
                patch_resp = self.endpoint.patch(
                    endpoint_id=resource_id, data={"category": category_id}
                )
                patch_resp.raise_for_status()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to patch category for resource {resource_id}: "
                    f"{getattr(patch_resp, 'status_code', '?')} "
                    f"{getattr(patch_resp, 'text', '')}"
                ) from exc

        tags_list = self._get_tags(row)
        if tags_list:
            self.replace_tags(resource_id, tags_list)
            patch_resp = None
            try:
                patch_resp = self.endpoint.patch(
                    endpoint_id=resource_id, data={"tags": tags}
                )
                patch_resp.raise_for_status()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to patch tags for resource {resource_id}: "
                    f"{getattr(patch_resp, 'status_code', '?')} "
                    f"{getattr(patch_resp, 'text', '')}"
                ) from exc
        if title := self._get_title(row):
            patch_resp = None
            try:
                patch_resp = self.endpoint.patch(
                    endpoint_id=resource_id, data={"title": title}
                )
                patch_resp.raise_for_status()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to patch title for resource {resource_id}: "
                    f"{getattr(patch_resp, 'status_code', '?')} "
                    f"{getattr(patch_resp, 'text', '')}"
                ) from exc

        path_col = self._find_path_col()
        if path_col and path_col in row:
            folder_path = self._resolve_folder(row[path_col])

            # Attaches files from path if directory or file
            if folder_path and folder_path.exists() and folder_path.is_dir():
                self.attach_files(resource_id, folder_path)
            elif folder_path and folder_path.exists() and folder_path.is_file():
                self.attach_single_file(resource_id, folder_path)
            elif folder_path:
                logger.warning("Files path does not exist: %s", folder_path)

        known = {canonicalize_field(name) for name in self._KNOWN_POST_FIELDS}
        if path_col:
            known.add(canonicalize_field(path_col))
        self.post_extra_fields_from_row(resource_id, row, known_columns=known)

        self._new_resources_counter += 1
        return resource_id

    def patch_existing(self, resource_id: str, category: str, row: pd.Series) -> Any:
        payload: dict[str, Any] = {"category": category}

        if tags := self._get_tags_str(row):
            payload["tags"] = tags

        if title := self._get_title(row):
            payload["title"] = title

        if date := self._normalize_date(row):
            payload["date"] = date

        existing_json = self.get_existing_json(resource_id)
        raw_metadata = existing_json.get("metadata") or {}

        if isinstance(raw_metadata, str):
            try:
                metadata = json.loads(raw_metadata)
            except Exception:
                metadata = {}
        else:
            metadata = raw_metadata

        extra_fields = metadata.setdefault("extra_fields", {})
        metadata["extra_fields"] = {k.lower(): v for k, v in extra_fields.items()}

        metadata_str = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))

        payload["metadata"] = metadata_str

        response = self.endpoint.patch(endpoint_id=resource_id, data=payload)
        response.raise_for_status()

        logger.info("Patched resource %s", resource_id)
        return response.status_code

    def create_all_from_csv(self, template: int | str | None = None) -> list[str]:
        """Create every resource row in the CSV; optional template override per call."""
        ids: list[str] = []
        for _, row in self.basic_df.iterrows():
            ids.append(self.create_new(row=row, template=template))
        return ids
