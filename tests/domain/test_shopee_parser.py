from datetime import date

from app.domain.platforms import shopee
from app.domain.types import Platform


def rec(**kw):
    return kw


def test_parse_income_happy_and_sums_same_order_same_day():
    result = shopee.parse_income([
        (4, rec(order_id="A1", settled_at="2026-09-15", net_received="285.00", commission_fee="-10", affiliate_fee="-5")),
        (5, rec(order_id="A1", settled_at="2026-09-15", net_received="15.00", other_adjustment="15")),
        (6, rec(order_id=260900000000123.0, settled_at="16/09/2026", net_received="99.50")),
    ])
    assert result.problems == ()
    a1, a2 = result.values
    assert a1.platform is Platform.SHOPEE and a1.order_id == "A1"
    assert a1.net_received == 30000 and a1.commission_fee == -1000 and a1.other_adjustment == 1500
    assert a1.settlement_key == ("shopee", "A1", date(2026, 9, 15))
    assert a2.order_id == "260900000000123" and a2.net_received == 9950


def test_parse_income_reports_problems_and_keeps_good_rows():
    result = shopee.parse_income([
        (4, rec(order_id="", settled_at="2026-09-15", net_received="1")),
        (5, rec(order_id="B", settled_at="soon", net_received="1")),
        (6, rec(order_id="C", settled_at="2026-09-15", net_received="")),
        (7, rec(order_id="D", settled_at="2026-09-15", net_received="10", commission_fee="x")),
        (8, rec(order_id="E", settled_at="2026-09-15", net_received="10")),
    ])
    assert [v.order_id for v in result.values] == ["E"]
    assert [(p.row_no, p.field) for p in result.problems] == [(4, "order_id"), (5, "settled_at"), (6, "net_received"), (7, "commission_fee")]


def test_parse_orders_assigns_line_no_per_order():
    result = shopee.parse_orders([
        (2, rec(order_id="A1", ordered_at="2026-09-10 10:00", sku="PNC-001", quantity="2", status="สำเร็จ", payment_method="เก็บเงินปลายทาง")),
        (3, rec(order_id="A1", ordered_at="2026-09-10 10:00", sku="PNC-002", quantity=1)),
        (4, rec(order_id="A2", ordered_at="2026-09-11", sku="", product_name="", quantity=1)),
    ])
    assert [(ln.order_id, ln.line_no, ln.sku, ln.quantity) for ln in result.values] == [("A1", 1, "PNC-001", 2), ("A1", 2, "PNC-002", 1)]
    assert result.values[0].payment_method == "เก็บเงินปลายทาง"
    assert result.problems[0].field == "product_name"
