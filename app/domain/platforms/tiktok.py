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


def _payment_method(description: str) -> str:
    return description.split(":", 1)[1].strip() if ":" in description else description.strip()


def parse_ads(records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[Expense]:
    """Ads Manager statement (ADR-0007). Only bills paid outside the payout become ads Expenses.
    Bills paid by GMV Pay are already imported from the income statement (ADR-0005); ad credit is not cash."""
    opts = options or {}
    charge_subtypes = {s.strip() for s in opts.get("charge_subtypes", ())}
    success = {s.strip() for s in opts.get("success_statuses", ())}
    free_funds = {s.strip() for s in opts.get("free_fund_types", ())}
    charged = {s.strip() for s in opts.get("charged_payment_methods", ())}
    from_payout = {s.strip() for s in opts.get("payout_payment_methods", ())}
    charges: list[Expense] = []
    problems: list[ImportProblem] = []
    skipped_payout = skipped_free = 0
    for row_no, rec in records:
        if _common.text(rec.get("fund_type")) in free_funds:
            skipped_free += 1
            continue
        status, subtype = _common.text(rec.get("status")), _common.text(rec.get("transaction_subtype"))
        if status not in success:
            problems.append(ImportProblem(f"สถานะ '{status}' ไม่ใช่รายการสำเร็จ — ข้ามแถว", row_no, "status"))
            continue
        if subtype not in charge_subtypes:
            problems.append(ImportProblem(f"ไม่รู้จักประเภทธุรกรรม '{subtype}' — ข้ามแถว", row_no, "transaction_subtype"))
            continue
        method = _payment_method(_common.text(rec.get("description")))
        if method in from_payout:
            skipped_payout += 1
            continue
        if method not in charged:
            problems.append(ImportProblem(f"ไม่รู้จักวิธีจ่าย '{method}' — ข้ามแถว ตรวจว่าจ่ายจากยอดโอนหรือจ่ายเอง", row_no, "description"))
            continue
        ref = _common.text(rec.get("transaction_id"))
        try:
            day = parse_date(_common.text(rec.get("transacted_at")))
            amount = parse_money(_common.text(rec.get("amount")))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่หรือยอดเงินไม่ได้", row_no, "amount"))
            continue
        if not ref:
            problems.append(ImportProblem("ไม่มีรหัสธุรกรรม", row_no, "transaction_id"))
            continue
        charges.append(Expense(ExpenseKind.ADS, PLATFORM.value, amount, day, f"TikTok Ads จ่ายด้วย {method} {ref}", source_ref=f"tiktok-ads:{ref}"))
    if skipped_payout:
        problems.append(ImportProblem(f"ข้าม {skipped_payout} แถวที่จ่ายด้วย {', '.join(sorted(from_payout))} (หักจากยอดโอน นำเข้าจากรายงานรายรับแล้ว)"))
    if skipped_free:
        problems.append(ImportProblem(f"ข้าม {skipped_free} แถว {', '.join(sorted(free_funds))} (เครดิตฟรี ไม่ใช่เงินที่จ่ายจริง)"))
    return ParseResult((), tuple(problems), tuple(charges))
