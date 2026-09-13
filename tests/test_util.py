import pytest

from bl.util import parse_duration_hours


def test_parse_duration_hours():
    assert parse_duration_hours("30d") == 30 * 24
    assert parse_duration_hours("12h") == 12
    assert parse_duration_hours("2w") == 2 * 24 * 7
    assert parse_duration_hours("7") == 7 * 24


def test_parse_duration_hours_invalid():
    with pytest.raises(ValueError):
        parse_duration_hours("banana")
