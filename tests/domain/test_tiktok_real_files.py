"""Spec from REAL TikTok Shop exports (tests/fixtures_tiktok_real.py). ADR-0005."""
from datetime import date
from pathlib import Path

import yaml

from app.domain import mapping
from app.domain.platforms import tiktok
from app.domain.types import ExpenseKind, Platform
from tests.fixtures_tiktok_real import INCOME_DETAIL_SHEET, INCOME_SUMMARY_SHEET, INCOME_WITHDRAW_SHEET, ORDERS_CSV_ROWS

TIKTOK = yaml.safe_load(Path("config/platforms/tiktok.yaml").read_text(encoding="utf-8"))


def _parse(kind, sheets):
    spec = mapping.spec_from_yaml(TIKTOK, kind)
    hit = mapping.find_header(sheets, spec)
    assert hit is not None
    si, ri = hit
    resolved = mapping.resolve(sheets[si][ri], spec)
    assert resolved.ok, resolved.missing_required
    return spec, mapping.to_records(sheets[si], ri, resolved)


def test_income_only_order_rows_become_settlements_and_refunds_are_separate_negative_settlements():
    spec, records = _parse("income", [INCOME_DETAIL_SHEET, INCOME_SUMMARY_SHEET, INCOME_WITHDRAW_SHEET])
    result = tiktok.parse_income(records, spec.options)
    assert result.problems == ()
    by_key = {(s.order_id, s.settled_at): s for s in result.values}
    assert all(s.platform is Platform.TIKTOK for s in result.values)
    # advance payout / deduction rows are ignored, charge rows are not settlements
    assert not any(s.order_id.startswith("3711") or s.order_id.startswith("1949") for s in result.values)
    s = by_key[("586246312794293667", date(2026, 9, 27))]
    assert s.net_received == 89487 and s.product_price == 121433
    assert (s.commission_fee, s.transaction_fee, s.platform_fee) == (-12993, -3898, -107)
    fees = s.commission_fee + s.service_fee + s.transaction_fee + s.affiliate_fee + s.tax_fee + s.platform_fee + s.ads_fee
    assert s.product_price + fees + s.shipping_fee_diff + s.other_adjustment == s.net_received
    # one order paid, then refunded on later days: three settlements, one per day
    ret = [v for (oid, d), v in by_key.items() if oid == "586113432168138545"]
    assert [x.net_received for x in sorted(ret, key=lambda x: x.settled_at)] == [108396, -129527, -5400]
    # a fully refunded order still yields a (zero) settlement
    assert by_key[("586263697824909058", date(2026, 9, 27))].net_received == 0


def test_income_charge_rows_become_expenses_with_source_ref():
    spec, records = _parse("income", [INCOME_DETAIL_SHEET])
    result = tiktok.parse_income(records, spec.options)
    charges = {c.source_ref: c for c in result.charges}
    ads = charges["tiktok:3709306954306913671"]
    assert (ads.kind, ads.platform, ads.amount, ads.incurred_on) == (ExpenseKind.ADS, "tiktok", 1610700, date(2026, 9, 23))
    fine = charges["tiktok:7685626791566477076"]
    assert (fine.kind, fine.amount) == (ExpenseKind.OTHER, 3500)
    assert len(charges) == 2


def test_orders_csv_product_key_returns_and_line_amount():
    spec, records = _parse("orders", [ORDERS_CSV_ROWS])
    result = tiktok.parse_orders(records, spec.options)
    assert result.problems == ()
    lines = result.values
    returned = next(ln for ln in lines if ln.order_id == "586113432168138545")
    assert returned.quantity == 0  # 1 ordered − 1 returned → no COGS
    assert returned.sku.endswith(" | 2แถม2") and returned.ordered_at == date(2026, 9, 17)
    assert returned.line_amount == 111200 and returned.payment_method == "PayLater"
    multi = [ln for ln in lines if ln.order_id == "585951609309005107"]
    assert [ln.line_no for ln in multi] == [1, 2]
    default_var = next(ln for ln in lines if ln.order_id == "585996677707498914")
    assert " | " not in default_var.sku  # "ค่าเริ่มต้น" is not a variation
    with_sku = next(ln for ln in lines if ln.order_id == "585871384241145788")
    assert with_sku.sku == "รสคุกกี้แอนด์ครีม 1"  # Seller SKU wins when present
    assert all(ln.platform is Platform.TIKTOK for ln in lines)
