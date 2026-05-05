import re

from elapi.validators import ValidationError, Validator

from src.utils.endpoints import get_fixed

_ID_PATTERN = re.compile(r"^\d+$|^me$", re.IGNORECASE)


class IDValidator(Validator):
    """Generic validator for any single-id endpoint."""

    def __init__(self, name: str, value: str | int):
        """name: endpoint type (“resource”, “category”, etc.); value: id to validate."""
        self.name = name
        self._value = str(value)
        self._endpoint = get_fixed(name)

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, v: str | int) -> None:
        if v is None:
            raise ValidationError(f"{self.name}_id cannot be None.")
        if not hasattr(v, "__str__"):
            raise ValidationError(f"{self.name}_id must be convertible to string.")
        self._value = str(v)



    def validate(self) -> int:
        if not _ID_PATTERN.match(self._value):
            raise ValidationError(f"Invalid {self.name}_id format.")
        try:
            resp = self._endpoint.get(endpoint_id=self._value)
            resp.raise_for_status()
            data = resp.json()
            item = data.get("data", data) if isinstance(data, dict) and "data" in data else data
            return int(item["id"])
        except KeyError:
            self._endpoint.close()
            raise
