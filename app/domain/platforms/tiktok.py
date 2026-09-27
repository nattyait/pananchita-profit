"""TikTok Shop adapter (ADR-0005). Pure.

Income file is an account statement: only rows whose transaction type is an order become Settlements;
charge rows (ads, fines) become Expenses; advance payout / deduction rows are ignored.
"""
from __future__ import annotations

from typing import Any

from app.domain.dates import parse_date
from app.domain.money import parse_money, parse_money_or_zero
from app.domain.platforms import _common
from app.domain.types import Expense, ExpenseKind, ImportProblem, OrderLine, ParseResult, Platform, Settlement

PLATFORM = Platform.TIKTOK
_AFFILIATE = ("affiliate_fee", "affiliate_partner_fee", "affiliate_ads_fee", "affiliate_ads_partner_fee")


def _m(rec: dict[str, Any], f: str) -> int:
    return parse_money_or_zero(_common.text(rec.get(f))) if f in rec else 0


def parse_income(records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[Settlement]:
    opts = options or {}
    order_types = {s.strip() for s in opts.get("order_types", ())}
    charge_types = {k.strip(): v for k, v in (opts.get("charge_types") or {}).items()}
    ignore_types = {s.strip() for s in opts.get("ignore_types", ())}
    grouped: dict[tuple[str, Any], Settlement] = {}
    charges: list[Expense] = []
    problems: list[ImportProblem] = []
    for row_no, rec in records:
        ttype = _common.text(rec.get("transaction_type"))
        ref = _common.text(rec.get("order_id"))
        if ttype in ignore_types:
            continue
        try:
            day = parse_date(_common.text(rec.get("settled_at")))
            amount = parse_money(_common.text(rec.get("net_received")))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่หรือยอดเงินไม่ได้", row_no, "net_received"))
            continue
        if ttype in charge_types:
            charges.append(Expense(ExpenseKind(charge_types[ttype]), PLATFORM.value, -amount, day, f"TikTok {ttype} {ref}", source_ref=f"tiktok:{ref}"))
            continue
        if ttype not in order_types:
            problems.append(ImportProblem(f"ไม่รู้จักประเภทธุรกรรม '{ttype}' — ข้ามแถว", row_no, "transaction_type"))
            continue
        if not ref:
            problems.append(ImportProblem("ไม่มีหมายเลขคำสั่งซื้อ", row_no, "order_id"))
            continue
        try:
            product_price = _m(rec, "product_price")
            fee_total = _m(rec, "fee_total")
            commission, transaction, platform_fee = _m(rec, "commission_fee"), _m(rec, "transaction_fee"), _m(rec, "platform_fee")
            affiliate = sum(_m(rec, f) for f in _AFFILIATE)
            ads, shipping = _m(rec, "ads_fee"), _m(rec, "shipping_fee_diff")
        except ValueError:
            problems.append(ImportProblem("อ่านค่าธรรมเนียมไม่ได้", row_no, "fee_total"))
            continue
        service = fee_total - (commission + transaction + affiliate + platform_fee)
        other = amount - (product_price + fee_total + shipping + ads)
        line = Settlement(PLATFORM, ref, day, amount, product_price=product_price, commission_fee=commission, service_fee=service,
                          transaction_fee=transaction, affiliate_fee=affiliate, platform_fee=platform_fee, ads_fee=ads,
                          shipping_fee_diff=shipping, other_adjustment=other)
        key = (ref, day)
        grouped[key] = _merge(grouped[key], line) if key in grouped else line
    return ParseResult(tuple(grouped.values()), tuple(problems), tuple(charges))


_SUMMED = ("product_price", "seller_discount", "commission_fee", "service_fee", "transaction_fee", "affiliate_fee", "tax_fee", "platform_fee",
           "ads_fee", "shipping_fee_diff", "other_adjustment")


def _merge(a: Settlement, b: Settlement) -> Settlement:
    return Settlement(a.platform, a.order_id, a.settled_at, a.net_received + b.net_received, **{f: getattr(a, f) + getattr(b, f) for f in _SUMMED})


def parse_orders(records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[OrderLine]:
    return _common.parse_orders(PLATFORM, records, options)
