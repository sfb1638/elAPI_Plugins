from typing import Any

from src.services.importers.base_importer import BaseImporter
from src.services.importers.experiments_importer import ExperimentsImporter
from src.services.importers.resources_importer import ResourcesImporter


class ImporterFactory:
    _importers: dict[str, type[BaseImporter]] = {
        "resources": ResourcesImporter,
        "experiments": ExperimentsImporter,
    }

    @classmethod
    def get_importer(cls, name: str, *args: Any, **kwargs: Any) -> BaseImporter:
        importer_cls = cls._importers.get(name)
        if importer_cls is None:
            raise ValueError(f"No importer configured for '{name}'")
        return importer_cls(*args, **kwargs)
