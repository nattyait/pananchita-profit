"""Spec from REAL Shopee exports (tests/fixtures_shopee_real.py). ADR-0003."""
from datetime import date
from pathlib import Path

import yaml

from app.domain import mapping
from app.domain.platforms import shopee
from tests.fixtures_shopee_real import INCOME_SHEET, INCOME_SUMMARY_SHEET, ORDERS_ALL

SHOPEE = yaml.safe_load(Path("config/platforms/shopee.yaml").read_text(encoding="utf-8"))


def _parse(kind, sheets):
    spec = mapping.spec_from_yaml(SHOPEE, kind)
    hit = mapping.find_header(sheets, spec)
    assert hit is not None, "header not found"
    sheet_idx, row_idx = hit
    resolved = mapping.resolve(sheets[sheet_idx][row_idx], spec)
    assert resolved.ok, resolved.missing_required
    return spec, mapping.to_records(sheets[sheet_idx], row_idx, resolved)


def test_income_report_uses_second_sheet_and_real_headers():
    spec, records = _parse("income", [INCOME_SUMMARY_SHEET, INCOME_SHEET])
    result = shopee.parse_income(records)
    assert result.problems == ()
    by_id = {s.order_id: s for s in result.values}
    assert len(by_id) == 6
    s = by_id["260811381HQ4V2"]  # affiliate order: 699 − 101 − 82 − 22 = 494
    assert s.settled_at == date(2026, 8, 18)
    assert s.net_received == 49400
    assert (s.commission_fee, s.affiliate_fee, s.transaction_fee, s.tax_fee) == (-10100, -8200, -2200, 0)
    assert s.shipping_fee_diff == 0  # 0 + 77 − 77
    t = by_id["260612UTFB6M06"]
    assert t.ads_fee == -1800 and t.tax_fee == 0 and t.net_received == 132900  # ads top-up charged from escrow
    # July total must reconcile with the monthly PDF statement (555 + 1,063)
    july = sum(x.net_received for x in by_id.values() if x.settled_at.month == 7)
    assert july == 161800


def test_orders_report_product_key_and_cancelled_flag():
    spec, records = _parse("orders", [ORDERS_ALL])
    result = shopee.parse_orders(records, spec.options)
    assert result.problems == ()
    lines = {ln.order_id: ln for ln in result.values}
    assert len(lines) == 3
    ln = lines["260811381HQ4V2"]
    assert ln.sku == "[โปร3ถง] AM WOW น้ำยาอเนกประสงค์ น้ำยาถูพื้น เช็ดกจระจก ล้างรถ ทำความสะอาด | กลิ่นมิ้นท์3ถุง"
    assert ln.quantity == 1 and ln.ordered_at == date(2026, 8, 11) and ln.payment_method == "เก็บเงินปลายทาง"
    assert ln.cancelled is False
    assert lines["260817JF6GNF53"].cancelled is True


def test_sku_wins_over_name_when_present():
    spec = mapping.spec_from_yaml(SHOPEE, "orders")
    rec = {"order_id": "A", "ordered_at": "2026-09-01", "sku": "PNC-001", "product_name": "ครีม", "variant_name": "30g", "quantity": 1, "status": "สำเร็จแล้ว"}
    result = shopee.parse_orders([(2, rec)], spec.options)
    assert result.values[0].sku == "PNC-001"


def test_name_only_when_no_variant():
    spec = mapping.spec_from_yaml(SHOPEE, "orders")
    rec = {"order_id": "A", "ordered_at": "2026-09-01", "sku": "", "product_name": " ครีม ", "variant_name": None, "quantity": 2, "status": ""}
    result = shopee.parse_orders([(2, rec)], spec.options)
    assert result.values[0].sku == "ครีม"


def test_orders_report_line_amount_from_unit_price():
    spec, records = _parse("orders", [ORDERS_ALL])
    lines = {ln.order_id: ln for ln in shopee.parse_orders(records, spec.options).values}
    assert lines["260811381HQ4V2"].line_amount == 69900  # 699.00 × 1
