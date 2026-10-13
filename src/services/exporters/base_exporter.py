from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class BaseExporter(ABC):
    @abstractmethod
    def xlsx_export(self, export_file: str | None = None) -> Path: ...

    @abstractmethod
    def fetch_data(
        self, start_offset: int = 0, page_size: int = 30, max_retries: int = 3
    ) -> pd.DataFrame: ...

    @abstractmethod
    def process_data(self) -> pd.DataFrame: ...
