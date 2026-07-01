from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import elapi.api
import pandas as pd

from src.utils.common import canonicalize as canonicalize_field
from src.utils.csv_tools import CsvTools
from src.utils.endpoints import get_fixed
from src.utils.logging_config import setup_logging
from src.utils.paths import EXP_IMPORTER_CONFIG

from .base_importer import BaseImporter

logger = logging.getLogger(__name__)

try:
    with open(EXP_IMPORTER_CONFIG, encoding="utf-8") as config_file:
        CONFIG = json.load(config_file)
except FileNotFoundError:
    raise FileNotFoundError(
        f"Config file not found. Tried: {EXP_IMPORTER_CONFIG}. "
        "Set EXP_IMPORTER_CONFIG to override, or ensure "
        "config/exp_importer_config.json exists at repo root."
    ) from None
except json.JSONDecodeError as exc:
    raise ValueError(f"Error decoding JSON from {EXP_IMPORTER_CONFIG}: {exc}") from exc


class ExperimentsImporter(BaseImporter):
    """Importer for the ElabFTW ``experiments`` endpoint."""

    _KNOWN_POST_FIELDS: set[str] = set(CONFIG["known_post_fields"])

    def __init__(
        self,
        csv_path: Path | str,
        files_base_dir: str | Path | None = None,
        template_id: int | str | None = None,
        category_id: int | str | None = None,
        update_existing: bool = False,
    ) -> None:
        setup_logging()
        self._endpoint: elapi.api.FixedEndpoint = get_fixed("experiments")
        self._experiments_df: pd.DataFrame = CsvTools.csv_to_df(csv_path)

        self._experiments_df.columns = (
            self._experiments_df.columns.astype(str)
            .str.replace("\u00a0", " ", regex=False)  # NBSP -> space
            .str.replace("\t", " ", regex=False)  # tabs -> space
            .str.strip()
        )

        rename_map = CsvTools.detect_field_rename(self._experiments_df.columns)
        if rename_map:
            self._experiments_df.rename(columns=rename_map, inplace=True)

        self._cols_canon: dict[str, str] = self._canonicalize_column_indexes(
            self._experiments_df.columns
        )
        self._template_id: int | str | None = template_id
        self._category_col: str | None = self.resolve_category_col()
        self._files_base_dir: Path | None = (
            Path(files_base_dir).expanduser() if files_base_dir else None
        )
        self._new_experiments_counter: int = 0
        self._patched_experiments_counter: int = 0
        self._skipped_experiments_counter: int = 0
        self._attached_files_counter: int = 0
        self._update_existing: bool = update_existing
        self._default_category: str | None = self.normalize_id(category_id)
        if self._default_category is not None:
            self.validate_category_id(self._default_category)

        self._experiment_id_col: str | None = (
            self._find_entity_id_col("experimentid") if self._update_existing else None
        )
        logger.info("Loaded experiments CSV with %d rows", len(self._experiments_df))

    # region --- Abstract interface ---

    @property
    def basic_df(self) -> pd.DataFrame:
        return self._experiments_df

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
        return self._new_experiments_counter

    @property
    def patched_count(self) -> int:
        return self._patched_experiments_counter

    @property
    def skipped_count(self) -> int:
        return self._skipped_experiments_counter

    def _increment_new_counter(self) -> None:
        self._new_experiments_counter += 1

    # endregion

    # region --- Entry patching ---

    def patch_existing(
        self, experiment_id: str, row: pd.Series, category: str | None = None
    ) -> Any:
        """
        Patch an existing experiment.

        Tags are replaced via /tags sub-endpoint (same semantics as create_new),
        because PATCHing {"tags": "..."} often does not update tags in ElabFTW.
        """
        payload: dict[str, Any] = {}

        if category:
            payload["category"] = category

        if title := self._get_title(row):
            payload["title"] = title

        vals_to_delete = row[row == "$delete_V"].index.tolist()
        fields_to_delete = row[row == "$delete_F"].index.tolist()

        row[vals_to_delete] = ""
        row.drop(fields_to_delete, inplace=True)

        body_col = self._find_col_like("body")
        if body_col and body_col in row:
            body_val = row[body_col]
            if not pd.isna(body_val) and str(body_val).strip():
                payload["body"] = str(body_val)

        if date := self._normalize_date(row):
            payload["date"] = date

        existing_json = self.get_existing_json(experiment_id)
        raw_metadata = existing_json.get("metadata") or {}

        if isinstance(raw_metadata, str):
            try:
                metadata = json.loads(raw_metadata)
            except Exception:
                metadata = {}
        else:
            metadata = raw_metadata

        metadata.setdefault("extra_fields", {})

        metadata_str = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        payload["metadata"] = metadata_str

        response = None
        if payload:
            response = self.endpoint.patch(endpoint_id=experiment_id, data=payload)
            response.raise_for_status()

        tags_list = self._get_tags(row)
        self.replace_tags(experiment_id, tags_list)

        path_col = self._find_path_col()
        if path_col and path_col in row:
            folder_path = self._resolve_folder(row[path_col])

            if folder_path and folder_path.exists():
                self.attach_files(experiment_id, folder_path)
            elif folder_path:
                logger.warning("Files path does not exist: %s", folder_path)

        known = {canonicalize_field(name) for name in self._KNOWN_POST_FIELDS}
        if path_col:
            known.add(canonicalize_field(path_col))
        self.post_extra_fields_from_row(experiment_id, row, known_columns=known)

        logger.info("Patched experiment %s", experiment_id)
        self._patched_experiments_counter += 1
        return getattr(response, "status_code", 200)

    # endregion

    # region --- CSV import ---

    def create_all_from_csv(self, template: int | str | None = None) -> list[str]:
        """Create or update experiments from the CSV depending on the update flag."""
        if self._update_existing:
            return self._import_update_existing()
        return self._import_new_experiments(template)

    def _import_new_experiments(self, template: int | str | None) -> list[str]:
        ids: list[str] = []
        for _, row in self.basic_df.iterrows():
            ids.append(self.create_new(row=row, template=template))
        return ids

    def _import_update_existing(self) -> list[str]:
        ids: list[str] = []
        if not self._experiment_id_col:
            msg = (
                "Update Existing is enabled but CSV has no 'Experiment ID' column. "
                "Add the column or disable update-existing."
            )
            logger.error(msg)
            raise ValueError(msg)

        for idx, row in self.basic_df.iterrows():
            experiment_id = self._parse_entity_id(self._experiment_id_col, row, row_index=idx, entity_label="Experiment")

            if not experiment_id:
                self._skipped_experiments_counter += 1
                continue
            category = self.get_category_id(row) or self._default_category

            if category is not None:
                self.validate_category_id(category)
            try:
                self.patch_existing(
                    experiment_id=experiment_id, row=row, category=category
                )
                ids.append(experiment_id)
            except Exception as exc:
                title = self._get_title(row) or "<untitled>"
                logger.warning(
                    "Skipping patch for Experiment ID %s (%s): %s",
                    experiment_id,
                    title,
                    exc,
                )
                self._skipped_experiments_counter += 1
        return ids

    # endregion
