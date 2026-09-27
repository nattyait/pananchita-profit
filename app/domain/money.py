"""Money parsing/formatting. Never float."""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_STRIP = re.compile(r"[฿$,\s]|THB", re.IGNORECASE)


def parse_money(value: object) -> int:
    """'1,234.50' | '(12.00)' | '-12' | 12.5 | Decimal → satang (int). Raises ValueError."""
    if value is None:
        raise ValueError("empty")
    if isinstance(value, bool):
        raise ValueError("bool is not money")
    if isinstance(value, int):
        return value * 100
    if isinstance(value, (float, Decimal)):
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), ROUND_HALF_UP))
    text = _STRIP.sub("", str(value))
    if text == "" or text == "-":
        raise ValueError("empty")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    try:
        dec = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc
    satang = int((dec * 100).quantize(Decimal("1"), ROUND_HALF_UP))
    return -satang if negative else satang


def parse_money_or_zero(value: object) -> int:
    """For OPTIONAL fee columns only: blank cell means 0. A non-blank unparsable cell still raises."""
    if value is None or (isinstance(value, str) and value.strip() in ("", "-")):
        return 0
    return parse_money(value)


def baht(satang: int) -> str:
    sign = "-" if satang < 0 else ""
    satang = abs(satang)
    return f"{sign}{satang // 100:,}.{satang % 100:02d}"
