from __future__ import annotations

import pytest
from elapi.validators import ValidationError

from src.utils import validators
from src.utils.validators import IDValidator
from tests.conftest import FakeEndpoint, FakeResponse


def test_id_validator_validate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = FakeEndpoint(get=lambda **kwargs: FakeResponse(json_data={"id": 7}))
    monkeypatch.setattr(validators, "get_fixed", lambda name: endpoint)

    validator = IDValidator("categories", 7)
    assert validator.validate() == 7


def test_id_validator_validate_success_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = FakeEndpoint(get=lambda **kwargs: FakeResponse(json_data={"data": {"id": 7}}))
    monkeypatch.setattr(validators, "get_fixed", lambda name: endpoint)

    validator = IDValidator("categories", 7)
    assert validator.validate() == 7


def test_id_validator_invalid_pattern_raises() -> None:
    validator = IDValidator("categories", "bad-id")
    with pytest.raises(ValidationError):
        validator.validate()
