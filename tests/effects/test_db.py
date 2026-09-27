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


def test_order_lines_roundtrip_and_skus_without_cost():
    s = _session()
    u = db.insert_upload(s, platform="shopee", kind="orders", filename="o.xlsx", sha256="3", uploaded_by="เก๋", uploaded_at=datetime(2026, 9, 1))
    db.insert_order_lines(s, u.id, (OrderLine(Platform.SHOPEE, "A", 1, "PNC-001", 2, date(2026, 9, 1), "ครีม"),))
    db.insert_sku_cost(s, sku="PNC-002", product_name="", unit_cost=100, effective_from=date(2026, 1, 1))
    assert db.all_order_lines(s)[0].sku == "PNC-001"
    assert db.known_skus_without_cost(s) == [("PNC-001", "ครีม")]
