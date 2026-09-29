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
    assert [(ln.order_id, ln.sku) for ln in d.lines] == [("A", "CAL | สตอเบอรี่ 1กล่อง"), ("B", "CAL | 2แถม2")]
    assert d.lines[0].profit == 30000 - 3802500


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
    assert [(ln.order_id, ln.empty_return) for ln in d.lines] == [("B", False), ("R", True)]
