import pytest

from src.validation import normalize_optional_iso_date, parse_iso_date, score_float, validate_date_window


def test_parse_iso_date_accepts_valid_date():
    assert parse_iso_date("2024-01-31") == "2024-01-31"


def test_parse_iso_date_rejects_invalid_format():
    with pytest.raises(ValueError):
        parse_iso_date("2024/01/31")


def test_normalize_optional_iso_date_strips_and_handles_empty():
    assert normalize_optional_iso_date(" 2024-02-01 ") == "2024-02-01"
    assert normalize_optional_iso_date("   ") is None
    assert normalize_optional_iso_date(None) is None


def test_validate_date_window_rejects_inverted_range():
    with pytest.raises(ValueError):
        validate_date_window("2024-12-31", "2024-01-01")


@pytest.mark.parametrize("value,expected", [("0.0", 0.0), ("0.5", 0.5), ("1.0", 1.0)])
def test_score_float_valid(value, expected):
    assert score_float(value) == expected


@pytest.mark.parametrize("value", ["1.5", "-0.1", "2.0"])
def test_score_float_out_of_range(value):
    with pytest.raises(ValueError, match=r"between 0\.0 and 1\.0"):
        score_float(value)


def test_score_float_invalid_string():
    with pytest.raises(ValueError):
        score_float("abc")
