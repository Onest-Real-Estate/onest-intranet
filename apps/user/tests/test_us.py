import pytest
from django.core.exceptions import ValidationError

from apps.user.us import normalize_nrds, normalize_us_phone, normalize_us_zip


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025550100", "(202) 555-0100"),
        ("(202) 555-0100", "(202) 555-0100"),
        ("+1 202-555-0100", "(202) 555-0100"),
        ("1.202.555.0100", "(202) 555-0100"),
    ],
)
def test_normalize_us_phone(raw, expected):
    assert normalize_us_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "0005550100", "202555010", "441234567890"])
def test_normalize_us_phone_rejects_invalid(raw):
    with pytest.raises(ValidationError):
        normalize_us_phone(raw)


def test_normalize_us_zip():
    assert normalize_us_zip("22030") == "22030"
    assert normalize_us_zip("22030-1234") == "22030-1234"


@pytest.mark.parametrize("raw", ["", "2203", "220301", "22030-123"])
def test_normalize_us_zip_rejects_invalid(raw):
    with pytest.raises(ValidationError):
        normalize_us_zip(raw)


def test_normalize_nrds():
    assert normalize_nrds("") == ""
    assert normalize_nrds("12345678") == "12345678"
    assert normalize_nrds("123-456-789") == "123456789"


def test_normalize_nrds_rejects_short():
    with pytest.raises(ValidationError):
        normalize_nrds("1234567")
