"""Additive schema migration: an old DB file gets new columns on open (ADR-0003)."""
from sqlalchemy import create_engine, inspect, text

from app.effects import db


def test_old_settlements_table_gains_new_columns(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE settlements (id INTEGER PRIMARY KEY, upload_id INTEGER, platform VARCHAR(16), order_id VARCHAR(64), "
                       "settled_at DATE, net_received INTEGER)"))
        c.execute(text("CREATE TABLE order_lines (id INTEGER PRIMARY KEY, upload_id INTEGER, platform VARCHAR(16), order_id VARCHAR(64), "
                       "line_no INTEGER, sku VARCHAR(80), quantity INTEGER, ordered_at DATE)"))
        c.execute(text("INSERT INTO settlements VALUES (1, 1, 'shopee', 'A', '2026-09-01', 100)"))
    db.make_session_factory(url)
    cols = {c["name"] for c in inspect(eng).get_columns("settlements")}
    assert {"tax_fee", "platform_fee", "commission_fee"} <= cols
    assert "cancelled" in {c["name"] for c in inspect(eng).get_columns("order_lines")}
    with eng.connect() as c:
        assert c.execute(text("SELECT tax_fee FROM settlements")).scalar() == 0
