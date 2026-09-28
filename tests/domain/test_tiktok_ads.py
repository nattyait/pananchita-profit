"""TikTok Ads Manager statement (Transaction_<account>_<time>.xlsx), ADR-0007. Rows are the real file of 2026-09."""
from datetime import date

from app.domain.platforms import tiktok
from app.domain.types import Expense, ExpenseKind

OPTIONS = {
    "charge_subtypes": ["Bill payment"],
    "success_statuses": ["Success"],
    "free_fund_types": ["Ad credit"],
    "charged_payment_methods": ["Credit or debit card"],
    "payout_payment_methods": ["GMV Pay"],
}
GMV, CARD = "Payment method:\nGMV Pay", "Payment method:\nCredit or debit card"
REAL = [
    ("2026/09/23 18:44", "Bill payment", "7688685895940145460", GMV, "Success", "Credit", "+16107.00"),
    ("2026/09/16 12:41", "Bill payment", "7685994819768811783", CARD, "Success", "Credit", "+181.83"),
    ("2026/09/16 12:40", "Bill payment", "7685994819768549639", GMV, "Success", "Credit", "+13745.49"),
    ("2026/09/15 13:17", "Issued", "7685267273770795282", "-", "Success", "Ad credit", "+302.01"),
    ("2026/09/14 11:44", "Issued", "7685080571545993479", "-", "Success", "Ad credit", "+277.67"),
    ("2026/09/08 22:38", "Bill payment", "7683178991949283585", CARD, "Success", "Credit", "+13584.52"),
    ("2026/09/08 22:37", "Issued", "7682582755998122247", "-", "Success", "Ad credit", "+1600.00"),
    ("2026/09/05 19:49", "Bill payment", "7682022907004256519", GMV, "Success", "Credit", "+12080.21"),
    ("2026/09/01 04:21", "Bill payment", "7680307153480220945", GMV, "Success", "Credit", "+5545.28"),
]
FIELDS = ("transacted_at", "transaction_subtype", "transaction_id", "description", "status", "fund_type", "amount")


def _records(rows):
    return [(i + 2, dict(zip(FIELDS, r, strict=True))) for i, r in enumerate(rows)]


def test_only_card_paid_bills_become_ads_expenses():
    result = tiktok.parse_ads(_records(REAL), OPTIONS)
    assert result.values == ()
    assert result.charges == (
        Expense(ExpenseKind.ADS, "tiktok", 18183, date(2026, 9, 16), "TikTok Ads จ่ายด้วย Credit or debit card 7685994819768811783",
                source_ref="tiktok-ads:7685994819768811783"),
        Expense(ExpenseKind.ADS, "tiktok", 1358452, date(2026, 9, 8), "TikTok Ads จ่ายด้วย Credit or debit card 7683178991949283585",
                source_ref="tiktok-ads:7683178991949283585"),
    )


def test_skipped_rows_are_reported_not_silent():
    msgs = [p.message for p in tiktok.parse_ads(_records(REAL), OPTIONS).problems]
    assert any("GMV Pay" in m and "4" in m for m in msgs)
    assert any("Ad credit" in m and "3" in m for m in msgs)


def test_unknown_payment_method_is_a_problem_not_an_expense():
    rows = [("2026/09/20 10:00", "Bill payment", "1", "Payment method:\nPromptPay", "Success", "Credit", "+100.00")]
    result = tiktok.parse_ads(_records(rows), OPTIONS)
    assert result.charges == () and "PromptPay" in result.problems[0].message and result.problems[0].row_no == 2


def test_failed_rows_and_unknown_subtypes_are_problems():
    rows = [("2026/09/20 10:00", "Bill payment", "1", CARD, "Failed", "Credit", "+100.00"),
            ("2026/09/20 10:00", "Refund", "2", CARD, "Success", "Credit", "-100.00")]
    result = tiktok.parse_ads(_records(rows), OPTIONS)
    assert result.charges == () and [p.row_no for p in result.problems] == [2, 3]
