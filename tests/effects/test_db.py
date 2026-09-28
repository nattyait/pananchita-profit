from datetime import date, datetime

from app.domain.types import OrderLine, Platform, Settlement
from app.effects import db


def _session():
    return db.make_session_factory("sqlite:///:memory:")()


def test_newest_upload_wins_for_same_settlement_key():
    s = _session()
    u1 = db.insert_upload(s, platform="shopee", kind="income", filename="a.xlsx", sha256="1", uploaded_by="เก๋", uploaded_at=datetime(2026, 9, 1))
    u2 = db.insert_upload(s, platform="shopee", kind="income", filename="b.xlsx", sha256="2", uploaded_by="เก๋", uploaded_at=datetime(2026, 9, 2))
    db.insert_settlements(s, u1.id, (Settlement(Platform.SHOPEE, "A", date(2026, 9, 5), 100),))
    db.insert_settlements(s, u2.id, (Settlement(Platform.SHOPEE, "A", date(2026, 9, 5), 120), Settlement(Platform.SHOPEE, "B", date(2026, 9, 6), 50)))
    got = {x.order_id: x.net_received for x in db.settlements_between(s, date(2026, 9, 1), date(2026, 9, 30))}
    assert got == {"A": 120, "B": 50}
    assert db.settlements_between(s, date(2026, 9, 6), date(2026, 9, 6))[0].order_id == "B"


def test_update_and_delete_sku_cost():
    s = _session()
    row = db.insert_sku_cost(s, sku="PNC-001", product_name="ครีม", unit_cost=100, effective_from=date(2026, 1, 1))
    db.update_sku_cost(s, row.id, sku="PNC-001", product_name="ครีม 30g", unit_cost=120, effective_from=date(2026, 2, 1))
    got = db.get_sku_cost(s, row.id)
    assert (got.product_name, got.unit_cost, got.effective_from) == ("ครีม 30g", 120, date(2026, 2, 1))
    db.delete_sku_cost(s, row.id)
    assert db.get_sku_cost(s, row.id) is None and db.all_sku_costs(s) == ()


def test_listing_map_marks_listing_covered_when_base_product_has_cost():
    s = _session()
    u = db.insert_upload(s, platform="tiktok", kind="orders", filename="o.csv", sha256="9", uploaded_by="เก๋", uploaded_at=datetime(2026, 9, 1))
    db.insert_order_lines(s, u.id, (OrderLine(Platform.TIKTOK, "T", 1, "[2แถม2] กาแฟ", 3, date(2026, 9, 1), "[2แถม2] กาแฟ"),))
    db.upsert_base_product(s, name="กาแฟ TikTok", unit_label="กล่อง")
    db.upsert_listing_map(s, sku="[2แถม2] กาแฟ", base_product="กาแฟ TikTok", units_per_listing=4, unit_price=20000)
    assert db.products_seen(s)[0].has_cost is False and db.products_seen(s)[0].base_product == "กาแฟ TikTok"
    db.insert_sku_cost(s, sku="กาแฟ TikTok", product_name="", unit_cost=5000, effective_from=date(2026, 1, 1))
    assert db.products_seen(s)[0].has_cost is True
    assert db.all_listing_maps(s)[0].units_per_listing == 4
    db.rename_base_product(s, old="กาแฟ TikTok", new="กาแฟ", unit_label="")
    assert db.all_listing_maps(s)[0].base_product == "กาแฟ" and db.all_sku_costs(s)[0].sku == "กาแฟ"
    assert db.products_seen(s)[0].has_cost is True
    db.delete_listing_map(s, "[2แถม2] กาแฟ")
    assert db.all_listing_maps(s) == ()


def test_order_lines_roundtrip_and_skus_without_cost():
    s = _session()
    u = db.insert_upload(s, platform="shopee", kind="orders", filename="o.xlsx", sha256="3", uploaded_by="เก๋", uploaded_at=datetime(2026, 9, 1))
    db.insert_order_lines(s, u.id, (OrderLine(Platform.SHOPEE, "A", 1, "PNC-001", 2, date(2026, 9, 1), "ครีม"),))
    db.insert_sku_cost(s, sku="PNC-002", product_name="", unit_cost=100, effective_from=date(2026, 1, 1))
    assert db.all_order_lines(s)[0].sku == "PNC-001"
    seen = db.products_seen(s)
    assert [(p.sku, p.product_name, p.quantity, p.order_count, p.has_cost) for p in seen] == [("PNC-001", "ครีม", 2, 1, False)]
