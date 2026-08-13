from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True)
class DateResolution:
    period_label: str
    calendar_range: DateRange
    fiscal_range: DateRange
    diverges: bool


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _calendar_quarter_range(today: date) -> DateRange:
    quarter_index = (today.month - 1) // 3
    start_month = quarter_index * 3 + 1
    start = date(today.year, start_month, 1)
    end_month = start_month + 2
    end_year = today.year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    end = _last_day_of_month(end_year, end_month)
    return DateRange(start, end)


def _calendar_year_range(today: date) -> DateRange:
    return DateRange(date(today.year, 1, 1), date(today.year, 12, 31))


def _fiscal_year_range(today: date) -> DateRange:
    if today.month >= 10:
        return DateRange(date(today.year, 10, 1), date(today.year + 1, 9, 30))
    return DateRange(date(today.year - 1, 10, 1), date(today.year, 9, 30))


class DateResolver:
    """Resolves relative date phrases ('this quarter', 'this year') against
    both calendar-date (Federal Register) and fiscal-year (USAspending)
    conventions, and flags when the two conventions actually produce
    different date ranges.

    Calendar quarters and federal fiscal quarters are the same 3-month
    windows (just numbered differently), so 'quarter' never diverges.
    Calendar year and fiscal year cover genuinely different 12-month
    windows, so 'year' always diverges.
    """

    def resolve(self, period: str, today: date) -> DateResolution:
        if period == "quarter":
            cal = _calendar_quarter_range(today)
            return DateResolution("quarter", cal, cal, diverges=False)
        if period == "year":
            cal = _calendar_year_range(today)
            fis = _fiscal_year_range(today)
            return DateResolution("year", cal, fis, diverges=(cal != fis))
        raise ValueError(f"unsupported period: {period!r}. Supported periods: 'quarter', 'year'.")
