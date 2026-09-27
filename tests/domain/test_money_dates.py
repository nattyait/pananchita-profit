from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.dates import in_period, parse_date
from app.domain.money import baht, parse_money, parse_money_or_zero


@pytest.mark.parametrize(
    "raw, satang",
    [
        ("1,234.50", 123450), ("฿1,234.50", 123450), ("-12", -1200), ("(12.00)", -1200),
        (12.5, 1250), (Decimal("0.1"), 10), (7, 700), ("0", 0), (" 99.99 ", 9999), ("1.005", 101),
    ],
)
def test_parse_money(raw, satang):
    assert parse_money(raw) == satang


@pytest.mark.parametrize("raw", [None, "", "-", "abc", True])
def test_parse_money_rejects(raw):
    with pytest.raises(ValueError):
        parse_money(raw)


def test_optional_money_blank_is_zero_but_garbage_still_raises():
    assert parse_money_or_zero("") == 0
    assert parse_money_or_zero(None) == 0
    with pytest.raises(ValueError):
        parse_money_or_zero("n/a")


def test_baht_format():
    assert baht(123450) == "1,234.50"
    assert baht(-5) == "-0.05"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-09-15 14:22:01", date(2026, 9, 15)), ("15/09/2026", date(2026, 9, 15)),
        (datetime(2026, 9, 15, 8), date(2026, 9, 15)), (date(2026, 1, 2), date(2026, 1, 2)),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_rejects():
    with pytest.raises(ValueError):
        parse_date("เมื่อวาน")


def test_in_period_inclusive():
    assert in_period(date(2026, 9, 1), date(2026, 9, 1), date(2026, 9, 30))
    assert in_period(date(2026, 9, 30), date(2026, 9, 1), date(2026, 9, 30))
    assert not in_period(date(2026, 10, 1), date(2026, 9, 1), date(2026, 9, 30))
