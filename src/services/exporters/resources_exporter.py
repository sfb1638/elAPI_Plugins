import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from werkzeug.utils import secure_filename

from src.utils.common import strip_html
from src.utils.endpoints import get_fixed
from src.utils.logging_config import setup_logging

from .base_exporter import BaseExporter

logger = logging.getLogger(__name__)


class ResourcesExporter(BaseExporter):
    def __init__(self, category_id: int) -> None:
        setup_logging()
        self._category_id = category_id
        self._endpoint = get_fixed("resources")

    def fetch_data(
        self, start_offset: int = 0, page_size: int = 1000, max_retries: int = 3
    ) -> pd.DataFrame:
        logger.info("Fetching resources for category %s", self._category_id)
        rows: list[dict] = []
        offset = start_offset

        while True:
            # full=1 makes eLabFTW return every column of each entry. Without it
            # the listing endpoint responds with a reduced record that carries
            # neither `metadata` (extra fields) nor `body`.
            resp = self._endpoint.get(
                query={
                    "cat": self._category_id,
                    "limit": page_size,
                    "offset": offset,
                    "full": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            page = data["data"] if isinstance(data, dict) and "data" in data else data
            page_rows = list(page)
            logger.debug(
                "Fetched %d resources (offset=%d, limit=%d)",
                len(page_rows),
                offset,
                page_size,
            )
            rows.extend(page_rows)

            if len(page_rows) < page_size:
                break
            offset += page_size

        return pd.json_normalize(rows)

    def process_data(self) -> pd.DataFrame:
        df = self.fetch_data()

        cols_to_drop = [
            "team",
            "elabid",
            "category",
            "locked",
            "lockedby",
            "locked_at",
            "userid",
            "canread",
            "canwrite",
            "available",
            "lastchangeby",
            "state",
            "events_start",
            "content_type",
            "created_at",
            "access_key",
            "is_bookable",
            "canbook",
            "book_max_minutes",
            "book_max_slots",
            "book_can_overlap",
            "book_is_cancellable",
            "book_cancel_minutes",
            "status",
            "custom_id",
            "timestamped",
            "timestampedby",
            "timestamped_at",
            "book_users_can_in_past",
            "is_procurable",
            "proc_pack_qty",
            "proc_price_notax",
            "proc_price_tax",
            "proc_currency",
            "page",
            "type",
            "status_color",
            "category_color",
            "recent_comment",
            "has_comment",
            "tags_id",
            "events_start_itemid",
            "next_step",
            "firstname",
            "lastname",
            "orcid",
            "up_item_id",
        ]
        df_clean = df.drop(columns=cols_to_drop + ["metadata"], errors="ignore")

        # `metadata_decoded` duplicates `metadata`; json_normalize expands it into
        # one column per field *attribute* (type, group_id, description, ...), so
        # drop it along with any flattened children.
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
            out_path = Path.cwd() / f"category_{self._category_id}_{ts}.xlsx"

        out_path.parent.mkdir(exist_ok=True, parents=True)
        export_data.to_excel(out_path, index=False)
        logger.info("Exported %d resources to %s", len(export_data), out_path)
        return out_path
