"""These tests ARE the spec for OrderProfit / PeriodPnl (ADR-0002)."""
from datetime import date

from app.domain.profit import build_report, cogs_for, effective_cost
from app.domain.types import SHARED, Expense, ExpenseKind, OrderLine, Platform, Settlement, SkuCost

SEP1, SEP30 = date(2026, 9, 1), date(2026, 9, 30)
COSTS = (SkuCost("PNC-001", 5000, date(2026, 1, 1)), SkuCost("PNC-001", 6000, date(2026, 9, 15)), SkuCost("PNC-002", 8000, date(2026, 1, 1)))


def sett(order_id, day, net, platform=Platform.SHOPEE, **fees):
    return Settlement(platform, order_id, day, net, **fees)


def line(order_id, sku, qty, day, platform=Platform.SHOPEE, **kw):
    return OrderLine(platform, order_id, 1, sku, qty, day, **kw)


def test_effective_cost_uses_cost_in_force_on_ordered_at():
    assert effective_cost(COSTS, "PNC-001", date(2026, 9, 14)) == 5000
    assert effective_cost(COSTS, "PNC-001", date(2026, 9, 15)) == 6000
    assert effective_cost(COSTS, "PNC-001", date(2025, 12, 31)) is None


def test_cogs_unknown_sku_is_none_not_zero():
    cogs, problems = cogs_for((line("A", "NOPE", 1, SEP1),), COSTS)
    assert cogs is None and "NOPE" in problems[0].message


def test_revenue_only_from_settlement_and_period_by_settled_at():
    r = build_report(
        period_start=SEP1, period_end=SEP30,
        settlements=(sett("A", date(2026, 9, 5), 30000), sett("B", date(2026, 10, 1), 99999)),  # B settled in Oct
        order_lines=(line("A", "PNC-001", 2, date(2026, 8, 28)), line("B", "PNC-002", 1, date(2026, 9, 2))),  # A ordered in Aug
        sku_costs=COSTS, expenses=(),
    )
    assert r.total.net_received == 30000
    assert r.total.cogs == 10000
    assert [o.order_id for o in r.orders] == ["A"]
    assert r.total.net_profit == 20000
    assert r.pending == ()  # B has a settlement (just not in period) → not pending


def test_pending_order_without_settlement_is_listed_not_zero():
    r = build_report(
        period_start=SEP1, period_end=SEP30, settlements=(),
        order_lines=(line("COD1", "PNC-001", 1, date(2026, 9, 20), status="กำลังจัดส่ง", payment_method="เก็บเงินปลายทาง"),),
        sku_costs=COSTS, expenses=(),
    )
    assert r.orders == () and r.total.net_received == 0
    assert r.pending[0].order_id == "COD1" and r.pending[0].payment_method == "เก็บเงินปลายทาง"


def test_cancelled_order_is_not_pending():
    r = build_report(
        period_start=SEP1, period_end=SEP30, settlements=(),
        order_lines=(line("CANCEL1", "PNC-001", 1, date(2026, 9, 20), status="ยกเลิกแล้ว", cancelled=True),
                     line("OK1", "PNC-001", 1, date(2026, 9, 21))),
        sku_costs=COSTS, expenses=(),
    )
    assert [p.order_id for p in r.pending] == ["OK1"]


def test_settlement_without_order_lines_is_a_problem_and_cogs_incomplete():
    r = build_report(period_start=SEP1, period_end=SEP30, settlements=(sett("X", SEP1, 1000),), order_lines=(), sku_costs=COSTS, expenses=())
    assert r.orders[0].cogs is None and r.orders[0].profit is None
    assert r.total.cogs_incomplete_orders == 1
    assert "X" in r.problems[0].message


def test_shared_expense_allocated_by_net_received_share_and_sum_matches():
    settlements = (
        sett("S1", SEP1, 30000), sett("S2", SEP1, 10000),
        sett("T1", SEP1, 60000, platform=Platform.TIKTOK),
    )
    lines = (line("S1", "PNC-001", 1, SEP1), line("S2", "PNC-001", 1, SEP1), line("T1", "PNC-002", 1, SEP1, platform=Platform.TIKTOK))
    expenses = (
        Expense(ExpenseKind.STAFF, SHARED, 10000, date(2026, 9, 25)),
        Expense(ExpenseKind.ADS, "shopee", 4000, date(2026, 9, 3)),
        Expense(ExpenseKind.ADS, "tiktok", 999, date(2026, 8, 31)),  # outside period
    )
    r = build_report(period_start=SEP1, period_end=SEP30, settlements=settlements, order_lines=lines, sku_costs=COSTS, expenses=expenses)
    shopee, tiktok = r.by_platform["shopee"], r.by_platform["tiktok"]
    assert shopee.expenses == {ExpenseKind.STAFF: 4000, ExpenseKind.ADS: 4000}  # 40% of shared + own ads
    assert tiktok.expenses == {ExpenseKind.STAFF: 6000}
    assert r.total.expense_total == 14000
    by_id = {o.order_id: o for o in r.orders}
    assert by_id["S1"].allocated_expense == 6000 and by_id["S2"].allocated_expense == 2000  # 8000 split 3:1
    assert by_id["T1"].allocated_expense == 6000
    # invariant: Σ OrderProfit == PeriodPnl.net_profit when all COGS known
    assert sum(o.profit for o in r.orders) == r.total.net_profit == 100000 - 18000 - 14000


def test_platform_filter_keeps_only_that_platform_and_its_share():
    settlements = (sett("S1", SEP1, 30000), sett("T1", SEP1, 70000, platform=Platform.TIKTOK))
    lines = (line("S1", "PNC-001", 1, SEP1), line("T1", "PNC-002", 1, SEP1, platform=Platform.TIKTOK))
    expenses = (Expense(ExpenseKind.TAX, SHARED, 1000, SEP1), Expense(ExpenseKind.ADS, "tiktok", 500, SEP1))
    r = build_report(period_start=SEP1, period_end=SEP30, settlements=settlements, order_lines=lines, sku_costs=COSTS, expenses=expenses, platform=Platform.SHOPEE)
    assert list(r.by_platform) == ["shopee"]
    # Filtered view: shared expense is allocated only among visible platforms → whole 1000 to shopee.
    # (Cross-platform share needs the "all" view; documented in ADR-0002 consequences.)
    assert r.total.expenses == {ExpenseKind.TAX: 1000}
    assert r.total.net_received == 30000


def test_shared_expense_with_no_settlements_stays_in_total_unallocated():
    r = build_report(period_start=SEP1, period_end=SEP30, settlements=(), order_lines=(), sku_costs=COSTS,
                     expenses=(Expense(ExpenseKind.STAFF, SHARED, 20000, SEP1),))
    assert r.total.expense_total == 20000 and r.total.net_profit == -20000
    assert r.by_platform == {}


def test_order_money_is_split_across_lines_by_line_amount_and_sums_to_order_profit():
    """ADR-0004: two products in one order, 3:1 by line_amount."""
    settlements = (sett("M1", SEP1, 40000),)
    lines = (
        OrderLine(Platform.SHOPEE, "M1", 1, "PNC-001", 1, SEP1, line_amount=30000),
        OrderLine(Platform.SHOPEE, "M1", 2, "PNC-002", 2, SEP1, line_amount=10000),
    )
    expenses = (Expense(ExpenseKind.ADS, "shopee", 4000, SEP1),)
    r = build_report(period_start=SEP1, period_end=SEP30, settlements=settlements, order_lines=lines, sku_costs=COSTS, expenses=expenses)
    o = r.orders[0]
    a, b = o.lines
    assert (a.sku, a.net_received, a.cogs, a.allocated_expense) == ("PNC-001", 30000, 5000, 3000)
    assert (b.sku, b.net_received, b.cogs, b.allocated_expense) == ("PNC-002", 10000, 16000, 1000)
    assert a.profit + b.profit == o.profit == 40000 - 21000 - 4000
    assert r.by_product["PNC-002"].quantity == 2 and r.by_product["PNC-002"].net_profit == -7000
    assert r.by_product["PNC-001"].net_profit == 22000
    assert sum(p.net_profit for p in r.by_product.values()) == r.total.net_profit


def test_split_falls_back_to_quantity_when_no_line_amounts():
    settlements = (sett("M2", SEP1, 30000),)
    lines = (OrderLine(Platform.SHOPEE, "M2", 1, "PNC-001", 2, SEP1), OrderLine(Platform.SHOPEE, "M2", 2, "PNC-002", 1, SEP1))
    r = build_report(period_start=SEP1, period_end=SEP30, settlements=settlements, order_lines=lines, sku_costs=COSTS, expenses=())
    assert [ln.net_received for ln in r.orders[0].lines] == [20000, 10000]


def test_order_with_unknown_cost_has_no_line_profit_and_is_absent_from_products():
    r = build_report(period_start=SEP1, period_end=SEP30, settlements=(sett("U", SEP1, 1000),),
                     order_lines=(OrderLine(Platform.SHOPEE, "U", 1, "NOPE", 1, SEP1),), sku_costs=COSTS, expenses=())
    assert r.orders[0].lines[0].cogs is None and r.orders[0].lines[0].profit is None
    assert r.by_product == {}


def test_listing_map_multiplies_base_product_cost_and_reports_base_units():
    """ADR-0006: '[2แถม2] กาแฟ' = 4 boxes of base product 'กาแฟ TikTok' at 50/box → 200 per piece."""
    from app.domain.types import ListingMap

    costs = (SkuCost("กาแฟ TikTok", 5000, date(2026, 1, 1)),)
    maps = (ListingMap("[2แถม2] กาแฟ | ค่าเริ่มต้น", "กาแฟ TikTok", 4, 20000),)
    r = build_report(
        period_start=SEP1, period_end=SEP30, settlements=(sett("T1", SEP1, 70000, platform=Platform.TIKTOK),),
        order_lines=(OrderLine(Platform.TIKTOK, "T1", 1, "[2แถม2] กาแฟ | ค่าเริ่มต้น", 2, SEP1),),
        sku_costs=costs, expenses=(), listing_maps=maps,
    )
    assert r.orders[0].cogs == 2 * 4 * 5000 and r.total.net_profit == 70000 - 40000
    assert r.by_base_product["กาแฟ TikTok"].quantity == 8 and r.by_base_product["กาแฟ TikTok"].net_profit == 30000
    assert r.by_product["[2แถม2] กาแฟ | ค่าเริ่มต้น"].quantity == 2
    # mapped listing without base cost → problem names the base product
    r2 = build_report(period_start=SEP1, period_end=SEP30, settlements=(sett("T1", SEP1, 70000, platform=Platform.TIKTOK),),
                      order_lines=(OrderLine(Platform.TIKTOK, "T1", 1, "[2แถม2] กาแฟ | ค่าเริ่มต้น", 2, SEP1),), sku_costs=(), expenses=(), listing_maps=maps)
    assert r2.orders[0].cogs is None and "สินค้าฐาน กาแฟ TikTok" in r2.problems[0].message
