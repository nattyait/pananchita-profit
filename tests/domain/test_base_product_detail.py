from datetime import date

from app.domain.base_product_detail import SUSPICIOUS_UNITS, base_product_detail, suspicious_listing_skus
from app.domain.profit import build_report
from app.domain.types import ListingMap, OrderLine, Platform, Settlement, SkuCost

D = date(2026, 9, 10)
MAPS = (ListingMap("CAL | สตอเบอรี่ 1กล่อง", "CALCIUM PLUS", 195), ListingMap("CAL | 2แถม2", "CALCIUM PLUS", 4),
        ListingMap("CAL | 1กล่อง", "CALCIUM PLUS", 1), ListingMap("LOTION", "LOVE STORY", 1))


def _report():
    settlements = (Settlement(Platform.TIKTOK, "A", D, 30000), Settlement(Platform.TIKTOK, "B", D, 90000), Settlement(Platform.TIKTOK, "C", D, 20000))
    lines = (OrderLine(Platform.TIKTOK, "A", 1, "CAL | สตอเบอรี่ 1กล่อง", 1, D), OrderLine(Platform.TIKTOK, "B", 1, "CAL | 2แถม2", 1, D),
             OrderLine(Platform.TIKTOK, "C", 1, "LOTION", 1, D))
    costs = (SkuCost("CALCIUM PLUS", 19500, date(2026, 5, 1)), SkuCost("LOVE STORY", 14100, date(2026, 5, 1)))
    return build_report(period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), settlements=settlements, order_lines=lines,
                        sku_costs=costs, expenses=(), listing_maps=MAPS)


def test_detail_splits_a_base_product_by_listing_worst_first():
    d = base_product_detail(_report(), MAPS, "CALCIUM PLUS")
    assert [(r.sku, r.units_per_listing, r.order_count, r.pieces, r.base_units, r.cogs, r.net_profit) for r in d.listings] == [
        ("CAL | สตอเบอรี่ 1กล่อง", 195, 1, 1, 195, 3802500, 30000 - 3802500),
        ("CAL | 2แถม2", 4, 1, 1, 4, 78000, 90000 - 78000),
        ("CAL | 1กล่อง", 1, 0, 0, 0, 0, 0),  # mapped but not sold in the period: still listed so its units can be checked
    ]
    assert [(o.order_id, o.skus) for o in d.orders] == [("A", ("CAL | สตอเบอรี่ 1กล่อง",)), ("B", ("CAL | 2แถม2",))]
    assert d.orders[0].profit == 30000 - 3802500


def test_units_above_threshold_are_suspicious():
    assert SUSPICIOUS_UNITS == 20
    assert suspicious_listing_skus(MAPS) == frozenset({"CAL | สตอเบอรี่ 1กล่อง"})
    assert base_product_detail(_report(), MAPS, "CALCIUM PLUS").listings[0].suspicious


def test_fully_returned_orders_are_labelled_and_sorted_after_real_ones():
    settlements = (Settlement(Platform.TIKTOK, "R", D, 0), Settlement(Platform.TIKTOK, "B", D, 90000))
    lines = (OrderLine(Platform.TIKTOK, "R", 1, "CAL | 2แถม2", 0, D), OrderLine(Platform.TIKTOK, "B", 1, "CAL | 2แถม2", 1, D))
    report = build_report(period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), settlements=settlements, order_lines=lines,
                          sku_costs=(SkuCost("CALCIUM PLUS", 19500, date(2026, 5, 1)),), expenses=(), listing_maps=MAPS)
    d = base_product_detail(report, MAPS, "CALCIUM PLUS")
    assert [(o.order_id, o.empty_return) for o in d.orders] == [("B", False), ("R", True)]


def test_settlements_of_one_order_are_combined_into_one_row():
    # real case 585429565331244764: paid 670.48 on 10/08, clawed back 860.04 on 12/08 after a full return
    paid, back = date(2026, 8, 10), date(2026, 8, 12)
    settlements = (Settlement(Platform.TIKTOK, "T", paid, 67048), Settlement(Platform.TIKTOK, "T", back, -86004),
                   Settlement(Platform.TIKTOK, "K", paid, 90000))
    lines = (OrderLine(Platform.TIKTOK, "T", 1, "CAL | 2แถม2", 0, date(2026, 8, 7)), OrderLine(Platform.TIKTOK, "K", 1, "CAL | 2แถม2", 1, date(2026, 8, 7)))
    report = build_report(period_start=date(2026, 8, 1), period_end=date(2026, 8, 31), settlements=settlements, order_lines=lines,
                          sku_costs=(SkuCost("CALCIUM PLUS", 19500, date(2026, 5, 1)),), expenses=(), listing_maps=MAPS)
    d = base_product_detail(report, MAPS, "CALCIUM PLUS")
    t = d.orders[0]
    assert (t.order_id, t.settlement_count, t.first_settled_at, t.last_settled_at) == ("T", 2, paid, back)
    assert (t.received, t.clawed_back, t.net_received, t.cogs, t.profit) == (67048, -86004, -18956, 0, -18956)
    assert t.fully_returned and not t.empty_return
    k = d.orders[1]
    assert (k.order_id, k.settlement_count, k.pieces, k.cogs) == ("K", 1, 1, 78000)
