from datetime import date

from app.domain.missing_reports import ORDER_LOOKBACK_DAYS, MissingReport, missing_reports
from app.domain.profit import OrderLineProfit, OrderProfit, PendingOrder
from app.domain.types import Platform, ReportKind

TODAY = date(2026, 9, 28)


def _paid(platform, order_id, settled_at, with_lines):
    lines = (OrderLineProfit("SKU", "x", 1, 100, None, 0),) if with_lines else ()
    return OrderProfit(platform, order_id, settled_at, None, 100, None, 0, 0, 1, lines)


def _pending(platform, order_id, ordered_at):
    return PendingOrder(platform, order_id, ordered_at, "", "", 1)


def test_nothing_missing_asks_for_nothing():
    assert missing_reports([_paid(Platform.SHOPEE, "A", date(2026, 9, 5), True)], [], TODAY) == ()


def test_paid_orders_without_lines_ask_for_the_orders_report_per_platform_by_ordered_at():
    orders = [
        _paid(Platform.TIKTOK, "T1", date(2026, 9, 10), False),
        _paid(Platform.TIKTOK, "T2", date(2026, 9, 3), False),
        _paid(Platform.SHOPEE, "S1", date(2026, 9, 20), False),
        _paid(Platform.SHOPEE, "S2", date(2026, 9, 21), True),
    ]
    got = missing_reports(orders, [], TODAY)
    assert got == (
        MissingReport(Platform.SHOPEE, ReportKind.ORDERS, "ordered_at", date(2026, 8, 21), date(2026, 9, 20), 1),
        MissingReport(Platform.TIKTOK, ReportKind.ORDERS, "ordered_at", date(2026, 8, 4), date(2026, 9, 10), 2),
    )
    assert ORDER_LOOKBACK_DAYS == 30


def test_pending_orders_ask_for_the_income_report_by_settled_at_up_to_today():
    pending = [_pending(Platform.SHOPEE, "P1", date(2026, 9, 1)), _pending(Platform.SHOPEE, "P2", date(2026, 8, 25))]
    assert missing_reports([], pending, TODAY) == (
        MissingReport(Platform.SHOPEE, ReportKind.INCOME, "settled_at", date(2026, 8, 25), TODAY, 2),
    )


def test_orders_request_comes_before_income_request_for_the_same_platform():
    got = missing_reports([_paid(Platform.SHOPEE, "A", date(2026, 9, 5), False)], [_pending(Platform.SHOPEE, "P", date(2026, 9, 1))], TODAY)
    assert [r.kind for r in got] == [ReportKind.ORDERS, ReportKind.INCOME]
