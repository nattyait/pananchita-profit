"""Date parsing for platform reports. Pure."""
from __future__ import annotations

from datetime import date, datetime

_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%d-%m-%Y",
)


def parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise ValueError("empty date")
    text = str(value).strip()
    if not text:
        raise ValueError("empty date")
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {value!r}")


def in_period(day: date, start: date, end: date) -> bool:
    """Inclusive on both ends."""
    return start <= day <= end
