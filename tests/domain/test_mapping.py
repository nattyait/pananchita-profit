from pathlib import Path

import yaml

from app.domain.mapping import find_header_row, resolve, spec_from_yaml, to_records

SHOPEE = yaml.safe_load(Path("config/platforms/shopee.yaml").read_text(encoding="utf-8"))


def test_income_mapping_thai_headers():
    spec = spec_from_yaml(SHOPEE, "income")
    rows = [
        ["รายงานรายได้", None, None],
        ["ร้าน", "pananchita", None],
        ["หมายเลขคำสั่งซื้อ", "วันที่ปล่อยเงิน", "ค่าคอมมิชชั่น", "ค่าคอมมิชชั่น AMS", "ยอดเงินที่ปล่อยแล้ว", "ชื่อผู้ซื้อ"],
        ["2609A1", "2026-09-15", "-10.00", "-5.00", "285.00", "สมชาย"],
    ]
    idx = find_header_row(rows, spec)
    assert idx == 2
    m = resolve(rows[idx], spec)
    assert m.ok
    assert m.columns["net_received"] == 4
    assert m.columns["affiliate_fee"] == 3
    assert m.columns["commission_fee"] == 2  # exact "ค่าคอมมิชชั่น" must not grab the AMS column
    assert m.unmapped_headers == ("ชื่อผู้ซื้อ",)  # customer columns stay unmapped (privacy)
    recs = to_records(rows, idx, m)
    assert recs == [(4, {"order_id": "2609A1", "settled_at": "2026-09-15", "commission_fee": "-10.00", "affiliate_fee": "-5.00", "net_received": "285.00"})]


def test_missing_required_is_reported_not_guessed():
    spec = spec_from_yaml(SHOPEE, "income")
    m = resolve(["Order ID", "Commission Fee"], spec)
    assert not m.ok
    assert set(m.missing_required) == {"settled_at", "net_received"}


def test_header_row_not_found():
    spec = spec_from_yaml(SHOPEE, "orders")
    assert find_header_row([["a", "b"], ["c"]], spec) is None


def test_prefix_fallback_for_sku_header_with_suffix():
    spec = spec_from_yaml(SHOPEE, "orders")
    m = resolve(["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.) ", "จำนวน"], spec)
    assert m.ok and m.columns["sku"] == 3
