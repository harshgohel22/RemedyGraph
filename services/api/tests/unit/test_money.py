import pytest

from app.domain.money import parse_minor_units


def test_accepts_non_negative_int() -> None:
    assert parse_minor_units(0) == 0
    assert parse_minor_units(499900) == 499900


def test_rejects_float() -> None:
    with pytest.raises(ValueError, match="integer paise"):
        parse_minor_units(4999.0)


def test_rejects_bool() -> None:
    with pytest.raises(ValueError, match="integer paise"):
        parse_minor_units(True)


def test_rejects_negative() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        parse_minor_units(-1)
