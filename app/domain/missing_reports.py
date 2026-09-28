"""Which platform report staff should export next, and for which dates, so unmatched orders can be matched (pure)."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.profit import OrderProfit, PendingOrder
from app.domain.types import Platform, ReportKind

# Orders are placed before the money is released; export this many days before the first settled_at.
ORDER_LOOKBACK_DAYS = 30


@dataclass(frozen=True)
class MissingReport:
    platform: Platform
    kind: ReportKind
    date_field: str  # which date the export range filters on: "ordered_at" or "settled_at"
    start: date
    end: date
    order_count: int


def missing_reports(orders: Iterable[OrderProfit], pending: Iterable[PendingOrder], today: date) -> tuple[MissingReport, ...]:
    """Settlement without OrderLines → orders report by ordered_at. PendingOrder → income report by settled_at up to today."""
    no_lines: dict[Platform, list[date]] = defaultdict(list)
    for o in orders:
        if not o.lines:
            no_lines[o.platform].append(o.settled_at)
    unpaid: dict[Platform, list[date]] = defaultdict(list)
    for p in pending:
        unpaid[p.platform].append(p.ordered_at)
    out: list[MissingReport] = []
    for platform in sorted(set(no_lines) | set(unpaid), key=lambda p: p.value):
        if d := no_lines.get(platform):
            out.append(MissingReport(platform, ReportKind.ORDERS, "ordered_at", min(d) - timedelta(days=ORDER_LOOKBACK_DAYS), max(d), len(d)))
        if d := unpaid.get(platform):
            out.append(MissingReport(platform, ReportKind.INCOME, "settled_at", min(d), today, len(d)))
    return tuple(out)
