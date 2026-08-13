from datetime import date

import pytest

from civicpilot.date_resolver import DateRange, DateResolver


def test_quarter_never_diverges_because_quarters_are_calendar_aligned():
    resolver = DateResolver()
    res = resolver.resolve("quarter", today=date(2026, 8, 13))
    assert res.diverges is False
    assert res.calendar_range == res.fiscal_range
    assert res.calendar_range == DateRange(date(2026, 7, 1), date(2026, 9, 30))


def test_quarter_range_at_year_boundary():
    resolver = DateResolver()
    res = resolver.resolve("quarter", today=date(2026, 1, 15))
    assert res.diverges is False
    assert res.calendar_range == DateRange(date(2026, 1, 1), date(2026, 3, 31))


def test_year_diverges_before_fiscal_year_rolls_over():
    resolver = DateResolver()
    res = resolver.resolve("year", today=date(2026, 8, 13))
    assert res.diverges is True
    assert res.calendar_range == DateRange(date(2026, 1, 1), date(2026, 12, 31))
    assert res.fiscal_range == DateRange(date(2025, 10, 1), date(2026, 9, 30))


def test_year_diverges_after_fiscal_year_rolls_over_in_october():
    resolver = DateResolver()
    res = resolver.resolve("year", today=date(2026, 11, 1))
    assert res.diverges is True
    assert res.fiscal_range == DateRange(date(2026, 10, 1), date(2027, 9, 30))


def test_unsupported_period_raises():
    resolver = DateResolver()
    with pytest.raises(ValueError, match="unsupported period"):
        resolver.resolve("fortnight", today=date(2026, 1, 1))
