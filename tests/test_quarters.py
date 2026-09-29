from datetime import date

import pytest

from bankscreener.quarters import Quarter, latest_possible, quarter_range


def test_parse_and_format():
    q = Quarter.parse("2019q4")
    assert str(q) == "2019Q4"
    assert q.mmddyyyy == "12312019"
    assert Quarter.from_mmddyyyy("06302024") == Quarter(2024, 2)


def test_prev_next_wrap_years():
    assert Quarter(2020, 1).prev() == Quarter(2019, 4)
    assert Quarter(2019, 4).next() == Quarter(2020, 1)


def test_range():
    qs = quarter_range(Quarter(2019, 4), Quarter(2020, 3))
    assert [str(q) for q in qs] == ["2019Q4", "2020Q1", "2020Q2", "2020Q3"]


def test_bad_quarter():
    with pytest.raises(ValueError):
        Quarter.parse("2024Q5")
    with pytest.raises(ValueError):
        Quarter.from_mmddyyyy("05312024")


def test_latest_possible_waits_45_days():
    assert latest_possible(date(2026, 9, 29)) == Quarter(2026, 2)
    assert latest_possible(date(2026, 8, 1)) == Quarter(2026, 1)
    assert latest_possible(date(2026, 2, 20)) == Quarter(2025, 4)
