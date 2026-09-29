"""Shopee Ads wallet statement (nattyait_adwords_bill_<date>.csv), ADR-0007 amendment. Rows are the real file of 2026-09-29."""
from datetime import date

from app.domain.platforms import shopee
from app.domain.types import Expense, ExpenseKind

OPTIONS = {"charged_topups": ["เติมเครดิต"], "payout_topups": ["เติมเครดิตอัตโนมัติ (Escrow)"]}
REAL = [
    ("29/09/2026", "Deduction for Product Ad (Auto Bidding - GMV Max)", "-478.01"),
    ("29/09/2026", "โฆษณาแบบเลือกสินค้าอัตโนมัติ", "-35.20"),
    ("29/09/2026", "ค่าโฆษณาร้านค้า (ตั้งราคาประมูลเอง)", "-73.43"),
    ("28/09/2026", "Deduction for Product Ad (Auto Bidding - GMV Max)", "-6.96"),
    ("28/09/2026", "โฆษณาแบบเลือกสินค้าอัตโนมัติ", "-142.87"),
    ("28/09/2026", "ค่าโฆษณาร้านค้า (ตั้งราคาประมูลเอง)", "-23.82"),
    ("27/09/2026", "โฆษณาแบบเลือกสินค้าอัตโนมัติ", "-12.21"),
    ("27/09/2026", "Deduction for Product Ad (Auto Bidding - GMV Max)", "-0.00"),
    ("27/09/2026", "ค่าโฆษณา Live Ads", "-2.65"),
    ("27/09/2026", "ค่าโฆษณาร้านค้า (ตั้งราคาประมูลเอง)", "-73.02"),
    ("27/09/2026", "เติมเครดิต", "1000.00"),
    ("30/06/2026", "โฆษณาแบบเลือกสินค้าอัตโนมัติ", "-4.48"),
    ("29/06/2026", "โฆษณาแบบเลือกสินค้าอัตโนมัติ", "-12.52"),
    ("29/06/2026", "เติมเครดิตอัตโนมัติ (Escrow)", "17.00"),
]


def _records(rows):
    return [(i + 8, {"transacted_at": d, "description": t, "amount": a}) for i, (d, t, a) in enumerate(rows)]


def test_only_top_ups_the_shop_pays_itself_become_ads_expenses():
    result = shopee.parse_ads(_records(REAL), OPTIONS)
    assert result.values == ()
    assert result.charges == (
        Expense(ExpenseKind.ADS, "shopee", 100000, date(2026, 9, 27), "Shopee Ads เติมเครดิต", source_ref="shopee-ads:2026-09-27:เติมเครดิต:100000:1"),
    )


def test_spend_and_escrow_top_ups_are_reported_as_skipped():
    msgs = [p.message for p in shopee.parse_ads(_records(REAL), OPTIONS).problems]
    assert any("12 แถว" in m and "865.17" in m for m in msgs)  # wallet spend, not new cash
    assert any("1 แถว" in m and "Escrow" in m for m in msgs)


def test_two_identical_top_ups_on_one_day_are_both_kept():
    rows = [("27/09/2026", "เติมเครดิต", "500.00"), ("27/09/2026", "เติมเครดิต", "500.00")]
    refs = [c.source_ref for c in shopee.parse_ads(_records(rows), OPTIONS).charges]
    assert refs == ["shopee-ads:2026-09-27:เติมเครดิต:50000:1", "shopee-ads:2026-09-27:เติมเครดิต:50000:2"]


def test_unknown_money_coming_in_is_a_problem_not_an_expense():
    result = shopee.parse_ads(_records([("27/09/2026", "คืนเงินค่าโฆษณา", "120.00")]), OPTIONS)
    assert result.charges == () and "คืนเงินค่าโฆษณา" in result.problems[0].message and result.problems[0].row_no == 8
