from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from .money import ValidationError

DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%b %d %Y",
    "%d %b %Y",
    "%B %d %Y",
    "%d %B %Y",
)


def parse_date(value: object, *, field_name: str = "Date") -> date:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} is required.")
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
            if parsed.year < 1900 or parsed.year > 2200:
                raise ValidationError(f"{field_name} year is out of range.")
            return parsed
        except ValueError:
            continue
    try:
        parsed = date.fromisoformat(text)
        if parsed.year < 1900 or parsed.year > 2200:
            raise ValidationError(f"{field_name} year is out of range.")
        return parsed
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be a valid date.") from exc


def month_bounds(year: int, month: int) -> tuple[date, date]:
    if month < 1 or month > 12:
        raise ValidationError("Month must be 1-12.")
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_label_from_key(key: str) -> str:
    y, m = key.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


def iter_days(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
