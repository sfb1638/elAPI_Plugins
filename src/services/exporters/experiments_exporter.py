import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from werkzeug.utils import secure_filename

from src.utils.common import paged_fetch, strip_html
from src.utils.endpoints import get_fixed
from src.utils.logging_config import setup_logging

from .base_exporter import BaseExporter

logger = logging.getLogger(__name__)


class ExperimentsExporter(BaseExporter):
    def __init__(self) -> None:
        setup_logging()
        self._endpoint = get_fixed("experiments")

    def fetch_data(
        self, start_offset: int = 0, page_size: int = 30, max_retries: int = 3
    ) -> pd.DataFrame:
        logger.info(
            "Fetching experiments with page_size=%d start_offset=%d",
            page_size,
            start_offset,
        )

        def get_page(limit: int, offset: int) -> list[dict[str, Any]]:
            # full=1 makes eLabFTW return every column of each entry. Without it
            # the listing endpoint responds with a reduced record that carries
            # neither `metadata` (extra fields) nor `body`.
            resp = self._endpoint.get(
                query={"limit": limit, "offset": offset, "full": 1}
            )
            resp.raise_for_status()
            data = resp.json()
            if (
                isinstance(data, dict)
                and "data" in data
                and isinstance(data["data"], list)
            ):
                rows = data["data"]
            elif isinstance(data, list):
                rows = data
            else:
                rows = []
            return [row if isinstance(row, dict) else {} for row in rows]

        rows = list(
            paged_fetch(
                get_page,
                start_offset=start_offset,
                page_size=page_size,
                max_retries=max_retries,
            )
        )
        logger.info("Fetched %d experiments", len(rows))
        return pd.DataFrame(rows)

    def process_data(self) -> pd.DataFrame:
        df = self.fetch_data()

        if df.empty:
            logger.info("No experiments to export")
            return pd.DataFrame()

        cols_to_drop = [
            "userid",
            "created_at",
            "state",
            "content_type",
            "access_key",
            "custom_id",
            "page",
            "type",
            "status_color",
            "category",
            "category_color",
            "has_comment",
            "tags_id",
            "events_start",
            "events_start_itemid",
            "firstname",
            "lastname",
            "orcid",
            "up_item_id",
            "status",
            "locked_at",
            "locked",
            "timestamped",
            "team",
            # Internal identifiers and bookkeeping (already dropped for resources)
            "elabid",
            "lockedby",
            "lastchangeby",
            "timestampedby",
            "timestamped_at",
            "recent_comment",
            "next_step",
            # Permissions and plumbing
            "canread",
            "canwrite",
            "canread_base",
            "canwrite_base",
            "canread_is_immutable",
            "canwrite_is_immutable",
            "hide_main_text",
            "created_from_id",
            "created_from_type",
            "is_pinned",
            # Duplicate of `tags`
            "tags_decoded",
            # Signing
            "signature_count",
            "last_signed_at",
            "last_signed_by",
        ]

        df_clean = df.drop(columns=cols_to_drop + ["metadata"], errors="ignore")

        # `metadata_decoded` duplicates `metadata` and would land in the sheet as a
        # raw dict, so drop it along with any flattened children.
        df_clean = df_clean.drop(
            columns=[
                col
                for col in df_clean.columns
                if str(col).split(".")[0] == "metadata_decoded"
            ],
            errors="ignore",
        )

        if "metadata" not in df.columns:
            logger.warning(
                "Response has no 'metadata' column — extra fields cannot be "
                "exported. The API did not return full records (expected full=1)."
            )

        def _safe_metadata(meta: object) -> dict[str, Any]:
            if isinstance(meta, dict):
                return meta
            if meta is None:
                return {}
            if isinstance(meta, (float, int, complex, str, bytes, bool)):
                try:
                    if pd.isna(meta):
                        return {}
                except Exception:
                    pass
            try:
                loaded = json.loads(str(meta) or "{}")
                return loaded if isinstance(loaded, dict) else {}
            except Exception:
                return {}

        extra = []

        for meta_obj in df.get("metadata", []):
            data = _safe_metadata(meta_obj)
            fields = data.get("extra_fields", {})
            flat = {k: v.get("value") for k, v in fields.items() if isinstance(v, dict)}
            extra.append(flat)

        df_extra = pd.DataFrame(extra, index=df_clean.index)
        logger.info("Flattened %d extra field column(s)", len(df_extra.columns))
        df_final = pd.concat([df_clean, df_extra], axis=1)

        if "body" in df_final.columns:
            df_final["body"] = df_final["body"].fillna("").apply(strip_html)

        return df_final

    def xlsx_export(self, export_file: str | None = None) -> Path:
        export_data = self.process_data()

        if export_file:
            fn = secure_filename(export_file)
            if not fn.lower().endswith(".xlsx"):
                fn += ".xlsx"
            out_path = Path.cwd() / fn
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = Path.cwd() / f"experiments_export_{ts}.xlsx"

        out_path.parent.mkdir(exist_ok=True, parents=True)
        export_data.to_excel(out_path, index=False)
        logger.info("Exported %d experiments to %s", len(export_data), out_path)
        return out_path

#TODO
