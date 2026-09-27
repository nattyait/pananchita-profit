"""Shopee adapter: mapped records → Settlement / OrderLine. Pure.

Input records come from mapping.to_records(): (row_no, {field: raw cell}).
Multiple income lines for the same (order_id, settled_at) are summed into ONE Settlement,
because the settlement_key is (platform, order_id, settled_at) — see CLAUDE.md Domain Rules.
Header names live in config/platforms/shopee.yaml, locked against real exports (tests/fixtures_shopee_real.py).
"""
from __future__ import annotations

from typing import Any

from app.domain.dates import parse_date
from app.domain.money import parse_money, parse_money_or_zero
from app.domain.types import ImportProblem, OrderLine, ParseResult, Platform, Settlement

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


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():  # openpyxl may give 2.5e14 for long numeric ids
        return str(int(value))
    return str(value).strip()


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


def parse_income(records: list[tuple[int, dict[str, Any]]]) -> ParseResult[Settlement]:
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


def product_key(sku: str, product_name: str, variant_name: str) -> str:
    """ProductKey (ADR-0003): SKU if the shop set one, else 'product | variant' (or product alone)."""
    if sku:
        return sku
    return f"{product_name} | {variant_name}" if variant_name else product_name


def parse_orders(records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[OrderLine]:
    cancelled_statuses = {s.strip().lower() for s in (options or {}).get("cancelled_statuses", ())}
    lines: list[OrderLine] = []
    problems: list[ImportProblem] = []
    line_no_by_order: dict[str, int] = {}
    for row_no, rec in records:
        order_id = _text(rec.get("order_id"))
        if not order_id:
            problems.append(ImportProblem("ไม่มีหมายเลขคำสั่งซื้อ", row_no, "order_id"))
            continue
        try:
            ordered_at = parse_date(rec.get("ordered_at"))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่สั่งซื้อไม่ได้", row_no, "ordered_at"))
            continue
        product_name = _text(rec.get("product_name"))
        key = product_key(_text(rec.get("sku")), product_name, _text(rec.get("variant_name")))
        if not key:
            problems.append(ImportProblem("ไม่มีทั้ง SKU และชื่อสินค้า", row_no, "product_name"))
            continue
        try:
            qty = int(str(rec.get("quantity")).strip())
        except (TypeError, ValueError):
            problems.append(ImportProblem("อ่านจำนวนไม่ได้", row_no, "quantity"))
            continue
        status = _text(rec.get("status"))
        try:
            unit_price = parse_money_or_zero(rec.get("unit_price")) if "unit_price" in rec else 0
        except ValueError:
            problems.append(ImportProblem("อ่านราคาขายไม่ได้", row_no, "unit_price"))
            continue
        line_no_by_order[order_id] = line_no_by_order.get(order_id, 0) + 1
        lines.append(
            OrderLine(
                PLATFORM, order_id, line_no_by_order[order_id], key, qty, ordered_at,
                product_name=product_name, status=status, payment_method=_text(rec.get("payment_method")),
                cancelled=status.lower() in cancelled_statuses, line_amount=unit_price * qty,
            )
        )
    return ParseResult(tuple(lines), tuple(problems))
