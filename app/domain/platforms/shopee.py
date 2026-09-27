"""Shopee adapter: mapped records → Settlement / OrderLine. Pure.

Input records come from mapping.to_records(): (row_no, {field: raw cell}).
Multiple income lines for the same (order_id, settled_at) are summed into ONE Settlement,
because the settlement_key is (platform, order_id, settled_at) — see CLAUDE.md Domain Rules.
"""
from __future__ import annotations

from typing import Any

from app.domain.dates import parse_date
from app.domain.money import parse_money, parse_money_or_zero
from app.domain.types import ImportProblem, OrderLine, ParseResult, Platform, Settlement

PLATFORM = Platform.SHOPEE
_OPTIONAL_MONEY = (
    "product_price",
    "seller_discount",
    "commission_fee",
    "service_fee",
    "transaction_fee",
    "affiliate_fee",
    "shipping_fee_diff",
    "other_adjustment",
)


def _order_id(rec: dict[str, Any]) -> str:
    raw = rec.get("order_id")
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():  # openpyxl may give 2.5e14
        return str(int(raw))
    return str(raw).strip()


def parse_income(records: list[tuple[int, dict[str, Any]]]) -> ParseResult[Settlement]:
    grouped: dict[tuple[str, Any], Settlement] = {}
    problems: list[ImportProblem] = []
    for row_no, rec in records:
        order_id = _order_id(rec)
        if not order_id:
            problems.append(ImportProblem("ไม่มีหมายเลขคำสั่งซื้อ", row_no, "order_id"))
            continue
        try:
            settled_at = parse_date(rec.get("settled_at"))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่ปล่อยเงินไม่ได้", row_no, "settled_at"))
            continue
        try:
            net = parse_money(rec.get("net_received"))
        except ValueError:
            problems.append(ImportProblem("อ่านยอดเงินที่ปล่อยแล้วไม่ได้", row_no, "net_received"))
            continue
        fees: dict[str, int] = {}
        bad = False
        for f in _OPTIONAL_MONEY:
            try:
                fees[f] = parse_money_or_zero(rec.get(f)) if f in rec else 0
            except ValueError:
                problems.append(ImportProblem(f"อ่านค่า {f} ไม่ได้", row_no, f))
                bad = True
        if bad:
            continue
        line = Settlement(PLATFORM, order_id, settled_at, net, **fees)
        key = (order_id, settled_at)
        if key in grouped:
            grouped[key] = _merge(grouped[key], line)
        else:
            grouped[key] = line
    return ParseResult(tuple(grouped.values()), tuple(problems))


def _merge(a: Settlement, b: Settlement) -> Settlement:
    return Settlement(
        a.platform, a.order_id, a.settled_at, a.net_received + b.net_received,
        **{f: getattr(a, f) + getattr(b, f) for f in _OPTIONAL_MONEY},
    )


def parse_orders(records: list[tuple[int, dict[str, Any]]]) -> ParseResult[OrderLine]:
    lines: list[OrderLine] = []
    problems: list[ImportProblem] = []
    line_no_by_order: dict[str, int] = {}
    for row_no, rec in records:
        order_id = _order_id(rec)
        if not order_id:
            problems.append(ImportProblem("ไม่มีหมายเลขคำสั่งซื้อ", row_no, "order_id"))
            continue
        try:
            ordered_at = parse_date(rec.get("ordered_at"))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่สั่งซื้อไม่ได้", row_no, "ordered_at"))
            continue
        sku = str(rec.get("sku") or "").strip()
        if not sku:
            problems.append(ImportProblem("ไม่มี SKU", row_no, "sku"))
            continue
        try:
            qty = int(str(rec.get("quantity")).strip())
        except (TypeError, ValueError):
            problems.append(ImportProblem("อ่านจำนวนไม่ได้", row_no, "quantity"))
            continue
        line_no_by_order[order_id] = line_no_by_order.get(order_id, 0) + 1
        lines.append(
            OrderLine(
                PLATFORM, order_id, line_no_by_order[order_id], sku, qty, ordered_at,
                product_name=str(rec.get("product_name") or "").strip(),
                status=str(rec.get("status") or "").strip(),
                payment_method=str(rec.get("payment_method") or "").strip(),
            )
        )
    return ParseResult(tuple(lines), tuple(problems))
