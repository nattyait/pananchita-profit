"""Helpers shared by platform adapters. Pure. Each adapter passes only its yaml options."""
from __future__ import annotations

from typing import Any

from app.domain.dates import parse_date
from app.domain.money import parse_money_or_zero
from app.domain.types import ImportProblem, OrderLine, ParseResult, Platform


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():  # openpyxl may give 2.5e14 for long numeric ids
        return str(int(value))
    return str(value).strip()


def product_key(sku: str, product_name: str, variant_name: str) -> str:
    """ProductKey (ADR-0003): SKU if the shop set one, else 'product | variant' (or product alone)."""
    if sku:
        return sku
    return f"{product_name} | {variant_name}" if variant_name else product_name


def parse_orders(platform: Platform, records: list[tuple[int, dict[str, Any]]], options: dict[str, Any] | None = None) -> ParseResult[OrderLine]:
    opts = options or {}
    cancelled_statuses = {s.strip().lower() for s in opts.get("cancelled_statuses", ())}
    default_variations = {s.strip().lower() for s in opts.get("default_variations", ())}
    lines: list[OrderLine] = []
    problems: list[ImportProblem] = []
    line_no_by_order: dict[str, int] = {}
    for row_no, rec in records:
        order_id = text(rec.get("order_id"))
        if not order_id:
            problems.append(ImportProblem("ไม่มีหมายเลขคำสั่งซื้อ", row_no, "order_id"))
            continue
        try:
            ordered_at = parse_date(text(rec.get("ordered_at")))
        except ValueError:
            problems.append(ImportProblem("อ่านวันที่สั่งซื้อไม่ได้", row_no, "ordered_at"))
            continue
        product_name = text(rec.get("product_name"))
        variant = text(rec.get("variant_name"))
        if variant.lower() in default_variations:
            variant = ""
        key = product_key(text(rec.get("sku")), product_name, variant)
        if not key:
            problems.append(ImportProblem("ไม่มีทั้ง SKU และชื่อสินค้า", row_no, "product_name"))
            continue
        try:
            qty = int(text(rec.get("quantity")))
            returned = int(text(rec.get("returned_quantity")) or 0) if "returned_quantity" in rec else 0
        except (TypeError, ValueError):
            problems.append(ImportProblem("อ่านจำนวนไม่ได้", row_no, "quantity"))
            continue
        try:
            if "line_total" in rec and text(rec.get("line_total")):
                line_amount = parse_money_or_zero(text(rec.get("line_total")))
            else:
                line_amount = (parse_money_or_zero(rec.get("unit_price")) if "unit_price" in rec else 0) * qty
        except ValueError:
            problems.append(ImportProblem("อ่านราคาขายไม่ได้", row_no, "unit_price"))
            continue
        status = text(rec.get("status"))
        line_no_by_order[order_id] = line_no_by_order.get(order_id, 0) + 1
        lines.append(
            OrderLine(
                platform, order_id, line_no_by_order[order_id], key, max(qty - returned, 0), ordered_at,
                product_name=product_name, status=status, payment_method=text(rec.get("payment_method")),
                cancelled=status.lower() in cancelled_statuses, line_amount=line_amount, variant_name=variant,
            )
        )
    return ParseResult(tuple(lines), tuple(problems))
