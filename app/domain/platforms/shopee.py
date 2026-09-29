"""Shopee adapter: mapped records → Settlement / OrderLine. Pure.

Input records come from mapping.to_records(): (row_no, {field: raw cell}).
Multiple income lines for the same (order_id, settled_at) are summed into ONE Settlement,
because the settlement_key is (platform, order_id, settled_at) — see CLAUDE.md Domain Rules.
Header names live in config/platforms/shopee.yaml, locked against real exports (tests/fixtures_shopee_real.py).
"""
from __future__ import annotations

from typing import Any

from app.domain.dates import parse_date
from app.domain.money import baht, parse_money, parse_money_or_zero
from app.domain.platforms import _common
from app.domain.types import Expense, ExpenseKind, ImportProblem, OrderLine, ParseResult, Platform, Settlement

PLATFORM = Platform.SHOPEE
_FEE_FIELDS = (
    "product_price",
    "seller_discount",
    "commission_fee",
    "service_fee",
    "transaction_fee",
    "affiliate_fee",
    "tax_fee",
    "platform_fee",
    "ads_fee",
    "other_adjustment",
)
_SHIPPING_PARTS = ("shipping_buyer", "shipping_shopee", "shipping_charged", "shipping_fee_diff")
_SUMMED = _FEE_FIELDS + ("shipping_fee_diff",)


_text = _common.text


def _money_fields(rec: dict[str, Any], row_no: int, problems: list[ImportProblem]) -> dict[str, int] | None:
    out: dict[str, int] = {}
    bad = False
    for f in _FEE_FIELDS:
        try:
            out[f] = parse_money_or_zero(rec.get(f)) if f in rec else 0
        except ValueError:
            problems.append(ImportProblem(f"อ่านค่า {f} ไม่ได้", row_no, f))
            bad = True
    shipping = 0
    for f in _SHIPPING_PARTS:
        try:
            shipping += parse_money_or_zero(rec.get(f)) if f in rec else 0
        except ValueError:
            problems.append(ImportProblem(f"อ่านค่า {f} ไม่ได้", row_no, f))
            bad = True
    out["shipping_fee_diff"] = shipping
    return None if bad else out


def parse_income(records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[Settlement]:
    grouped: dict[tuple[str, Any], Settlement] = {}
    problems: list[ImportProblem] = []
    for row_no, rec in records:
        order_id = _text(rec.get("order_id"))
        if not order_id:
            problems.append(ImportProblem("ไม่มีหมายเลขคำสั่งซื้อ", row_no, "order_id"))
            continue
        try:
            settled_at = parse_date(rec.get("settled_at"))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่โอนเงินไม่ได้", row_no, "settled_at"))
            continue
        try:
            net = parse_money(rec.get("net_received"))
        except ValueError:
            problems.append(ImportProblem("อ่านจำนวนเงินที่โอนแล้วไม่ได้", row_no, "net_received"))
            continue
        fees = _money_fields(rec, row_no, problems)
        if fees is None:
            continue
        line = Settlement(PLATFORM, order_id, settled_at, net, **fees)
        key = (order_id, settled_at)
        grouped[key] = _merge(grouped[key], line) if key in grouped else line
    return ParseResult(tuple(grouped.values()), tuple(problems))


def _merge(a: Settlement, b: Settlement) -> Settlement:
    return Settlement(a.platform, a.order_id, a.settled_at, a.net_received + b.net_received, **{f: getattr(a, f) + getattr(b, f) for f in _SUMMED})


def parse_orders(records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[OrderLine]:
    return _common.parse_orders(PLATFORM, records, options)


def parse_ads(records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[Expense]:
    """Shopee Ads wallet statement (ADR-0007 amendment). Cash basis: only top-ups the shop pays itself become ads
    Expenses. Negative rows are ad credit being used (not new cash); Escrow auto top-ups are already deducted from the
    payout (Settlement.ads_fee). No transaction id in the file, so source_ref = date:description:amount:n-th same row."""
    opts = options or {}
    charged = {s.strip() for s in opts.get("charged_topups", ())}
    from_payout = {s.strip() for s in opts.get("payout_topups", ())}
    charges: list[Expense] = []
    problems: list[ImportProblem] = []
    spend_rows = spend_total = payout_rows = 0
    seen: dict[tuple, int] = {}
    for row_no, rec in records:
        desc = _common.text(rec.get("description"))
        try:
            day = parse_date(_common.text(rec.get("transacted_at")))
            amount = parse_money(_common.text(rec.get("amount")))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่หรือยอดเงินไม่ได้", row_no, "amount"))
            continue
        if amount <= 0:
            spend_rows += 1
            spend_total -= amount
            continue
        if desc in from_payout:
            payout_rows += 1
            continue
        if desc not in charged:
            problems.append(ImportProblem(f"ไม่รู้จักรายการเงินเข้า '{desc}' — ข้ามแถว ตรวจว่าเป็นการเติมเงินจากร้านหรือเงินคืน", row_no, "description"))
            continue
        key = (day, desc, amount)
        seen[key] = seen.get(key, 0) + 1
        charges.append(Expense(ExpenseKind.ADS, PLATFORM.value, amount, day, f"Shopee Ads {desc}",
                               source_ref=f"shopee-ads:{day.isoformat()}:{desc}:{amount}:{seen[key]}"))
    if spend_rows:
        problems.append(ImportProblem(f"ข้าม {spend_rows} แถวที่เป็นการใช้เครดิตโฆษณา รวม {baht(spend_total)} บาท (นับเป็นค่าใช้จ่ายตอนเติมเงินแล้ว)"))
    if payout_rows:
        problems.append(ImportProblem(f"ข้าม {payout_rows} แถวเติมเครดิตอัตโนมัติจาก Escrow (หักจากยอดโอน อยู่ในรายงานรายรับแล้ว)"))
    return ParseResult((), tuple(problems), tuple(charges))
