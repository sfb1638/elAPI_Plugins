"""Importers for eLabFTW templates (resource and experiment templates).

The API describes templates with ``entity_template_editable``, which extends the
same ``entity_editable`` schema as entries, so they accept title, body, metadata
(the extra-field definitions), permissions and tags.

Templates have no ``uploads`` or ``*_links`` sub-endpoints, so attachments and
entity links are unavailable and switched off via the capability flags.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import elapi.api
import pandas as pd

from src.utils.common import canonicalize as canonicalize_field
from src.utils.csv_tools import CsvTools
from src.utils.endpoints import get_fixed
from src.utils.logging_config import setup_logging

from .base_importer import BaseImporter

logger = logging.getLogger(__name__)

# Which eLabFTW endpoint each template kind lives on, and how to talk about it.
TEMPLATE_KINDS: dict[str, dict[str, str]] = {
    "resource_templates": {
        "endpoint": "resource_templates",
        "label": "Resource template",
    },
    "experiment_templates": {
        "endpoint": "experiment_templates",
        "label": "Experiment template",
    },
}


class TemplatesImporter(BaseImporter):
    """Create and update eLabFTW templates from a CSV.

    ``kind`` selects the endpoint: ``"resource_templates"`` (items_types) or
    ``"experiment_templates"`` (experiments_templates).
    """

    # Templates have neither uploads nor entity links.
    _SUPPORTS_UPLOADS = False
    _SUPPORTS_LINKS = False

    _KNOWN_POST_FIELDS: set[str] = {
        "title",
        "body",
        "tags",
        "category",
        "status",
        "date",
        "template",
    }

    # Set in __init__ when update-existing is enabled; declared here so the
    # attribute always exists.
    _template_row_id_col: str | None = None

    def __init__(
        self,
        csv_path: Path | str,
        kind: str = "resource_templates",
        files_base_dir: str | Path | None = None,
        template_id: int | str | None = None,
        category_id: int | str | None = None,
        update_existing: bool = False,
    ) -> None:
        setup_logging()

        if kind not in TEMPLATE_KINDS:
            raise ValueError(
                f"Unknown template kind {kind!r}. "
                f"Use one of: {', '.join(sorted(TEMPLATE_KINDS))}"
            )
        self._kind = kind
        self._label = TEMPLATE_KINDS[kind]["label"]

        self._endpoint: elapi.api.FixedEndpoint = get_fixed(
            TEMPLATE_KINDS[kind]["endpoint"]
        )
        self._templates_df: pd.DataFrame = CsvTools.csv_to_df(csv_path)

        self._templates_df.columns = (
            self._templates_df.columns.astype(str)
            .str.replace(" ", " ", regex=False)  # NBSP -> space
            .str.replace("\t", " ", regex=False)  # tabs -> space
            .str.strip()
        )

        rename_map = CsvTools.detect_field_rename(self._templates_df.columns)
        if rename_map:
            self._templates_df.rename(columns=rename_map, inplace=True)

        self._cols_canon: dict[str, str] = self._canonicalize_column_indexes(
            self._templates_df.columns
        )
        self._template_id: int | str | None = template_id
        self._category_col: str | None = self.resolve_category_col()
        self._files_base_dir: Path | None = (
            Path(files_base_dir).expanduser() if files_base_dir else None
        )
        self._new_templates_counter: int = 0
        self._patched_templates_counter: int = 0
        self._skipped_templates_counter: int = 0
        self._update_existing: bool = update_existing
        self._default_category: str | None = self.normalize_id(category_id)

        self._template_row_id_col: str | None = (
            self._find_entity_id_col("templateid") if self._update_existing else None
        )
        logger.info(
            "Loaded %s CSV with %d rows", self._label.lower(), len(self._templates_df)
        )

    # region --- Abstract interface ---

    @property
    def basic_df(self) -> pd.DataFrame:
        return self._templates_df

    @property
    def cols_canon(self) -> dict[str, str]:
        return self._cols_canon

    @property
    def endpoint(self) -> elapi.api.FixedEndpoint:
        return self._endpoint

    @property
    def files_base_dir(self) -> Path | None:
        return self._files_base_dir

    # endregion

    # region --- Counters ---

    @property
    def new_count(self) -> int:
        return self._new_templates_counter

    @property
    def patched_count(self) -> int:
        return self._patched_templates_counter

    @property
    def skipped_count(self) -> int:
        return self._skipped_templates_counter

    def _increment_new_counter(self) -> None:
        self._new_templates_counter += 1

    # endregion

    # region --- Entry patching ---

    def patch_existing(
        self, template_row_id: str, row: pd.Series, category: str | None = None
    ) -> Any:
        """Patch an existing template.

        Mirrors the resource/experiment behaviour: the title and extra fields are
        overwritten, the body is appended to, and tags are added to the existing
        ones. Attachments and links do not exist for templates.
        """
        payload: dict[str, Any] = {}

        if category:
            payload["category"] = category

        if title := self._get_title(row):
            payload["title"] = title

        vals_to_delete = row[row == "$delete_V"].index.tolist()
        fields_to_delete = row[row == "$delete_F"].index.tolist()
        rename_map = self._extract_rename_map(row)

        row[vals_to_delete] = ""
        if rename_map:
            row[list(rename_map.keys())] = ""
        row.drop(fields_to_delete, inplace=True)

        existing_json = self.get_existing_json(template_row_id)

        body_col = self._find_col_like("body")
        if body_col and body_col in row:
            body_val = row[body_col]
            if body_col in vals_to_delete:
                payload["body"] = ""
            elif not pd.isna(body_val) and str(body_val).strip():
                new_body = str(body_val)
                existing_body = existing_json.get("body") or ""
                payload["body"] = (
                    f"{existing_body}\n{new_body}" if existing_body else new_body
                )

        # Permissions: only the lists given in the CSV are replaced.
        payload.update(self.build_permission_payload(row, existing_json))

        response = None
        if payload:
            response = self.endpoint.patch(endpoint_id=template_row_id, data=payload)
            try:
                response.raise_for_status()
            except Exception:
                logger.error(
                    "PATCH failed for %s %s: %s %s | fields=%s body_len=%s",
                    self._label.lower(),
                    template_row_id,
                    getattr(response, "status_code", "?"),
                    getattr(response, "text", ""),
                    sorted(payload),
                    len(str(payload.get("body", ""))),
                )
                raise

        tags_list = self._get_tags(row)
        self.append_tags(
            template_row_id, tags_list, existing_tags=existing_json.get("tags")
        )

        known = {canonicalize_field(name) for name in self._KNOWN_POST_FIELDS}
        if self._template_row_id_col:
            known.add(canonicalize_field(self._template_row_id_col))

        # Templates have no uploads. Still exclude an attachments/path column so it
        # is skipped rather than silently stored as an extra field.
        path_col = self._find_path_col()
        if path_col:
            known.add(canonicalize_field(path_col))
            if path_col in row and str(row[path_col]).strip():
                logger.warning(
                    "%s do not support file attachments; ignoring column %r.",
                    self._label + "s",
                    path_col,
                )

        known |= {
            canonicalize_field(col)
            for col in self.find_permission_columns(row).values()
        }
        self.post_extra_fields_from_row(
            template_row_id,
            row,
            known_columns=known,
            delete_value_columns=vals_to_delete,
            delete_field_columns=fields_to_delete,
            rename_columns=rename_map,
        )

        logger.info("Patched %s %s", self._label.lower(), template_row_id)
        self._patched_templates_counter += 1
        return getattr(response, "status_code", 200)

    # endregion

    # region --- CSV import ---

    def create_all_from_csv(self, template: int | str | None = None) -> list[str]:
        """Create or update templates from the CSV depending on the update flag."""
        if self._update_existing:
            return self._import_update_existing()
        return self._import_new_templates(template)

    def _import_new_templates(self, template: int | str | None) -> list[str]:
        ids: list[str] = []
        for _, row in self.basic_df.iterrows():
            ids.append(self.create_new(row=row, template=template))
        return ids

    def _import_update_existing(self) -> list[str]:
        ids: list[str] = []
        if not self._template_row_id_col:
            msg = (
                "Update Existing is enabled but CSV has no 'Template ID' column. "
                "Add the column or disable update-existing."
            )
            logger.error(msg)
            raise ValueError(msg)

        for idx, row in self.basic_df.iterrows():
            template_row_id = self._parse_entity_id(
                self._template_row_id_col,
                row,
                row_index=idx,
                entity_label=self._label,
            )

            if not template_row_id:
                self._skipped_templates_counter += 1
                continue

            category = self.get_category_id(row) or self._default_category
            try:
                self.patch_existing(
                    template_row_id=template_row_id, row=row, category=category
                )
                ids.append(template_row_id)
            except Exception as exc:
                title = self._get_title(row) or "<untitled>"
                logger.warning(
                    "Skipping patch for %s %s (%s): %s",
                    self._label,
                    template_row_id,
                    title,
                    exc,
                )
                self._skipped_templates_counter += 1
        return ids

    # endregion


class ResourceTemplatesImporter(TemplatesImporter):
    """Importer for resource templates (``items_types``)."""

    def __init__(self, csv_path: Path | str, **kwargs: Any) -> None:
        kwargs.pop("kind", None)
        super().__init__(csv_path, kind="resource_templates", **kwargs)


class ExperimentTemplatesImporter(TemplatesImporter):
    """Importer for experiment templates (``experiments_templates``)."""

    def __init__(self, csv_path: Path | str, **kwargs: Any) -> None:
        kwargs.pop("kind", None)
        super().__init__(csv_path, kind="experiment_templates", **kwargs)
