"""Per-BaseProduct drill-down of a ProfitReport (pure, ADR-0006): which listing and which orders drive its number."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.domain.profit import ProfitReport
from app.domain.types import ListingMap, Platform

# More base units than this per sold piece is almost always a typo (e.g. the unit cost typed into the units box).
SUSPICIOUS_UNITS = 20


def suspicious_listing_skus(maps: Iterable[ListingMap]) -> frozenset[str]:
    return frozenset(m.sku for m in maps if m.units_per_listing > SUSPICIOUS_UNITS)


@dataclass(frozen=True)
class ListingBreakdown:
    sku: str
    units_per_listing: int
    order_count: int
    pieces: int
    net_received: int
    cogs: int
    expense: int

    @property
    def base_units(self) -> int:
        return self.pieces * self.units_per_listing

    @property
    def net_profit(self) -> int:
        return self.net_received - self.cogs - self.expense

    @property
    def suspicious(self) -> bool:
        return self.units_per_listing > SUSPICIOUS_UNITS


@dataclass(frozen=True)
class BaseProductLine:
    settled_at: date
    platform: Platform
    order_id: str
    sku: str
    pieces: int
    units_per_listing: int
    net_received: int
    cogs: int
    expense: int

    @property
    def profit(self) -> int:
        return self.net_received - self.cogs - self.expense

    @property
    def empty_return(self) -> bool:
        """Every piece came back and no money moved for this line."""
        return self.pieces == 0 and self.net_received == 0 and self.expense == 0


@dataclass(frozen=True)
class BaseProductDetail:
    name: str
    listings: tuple[ListingBreakdown, ...]  # sold ones worst net_profit first, then unsold
    lines: tuple[BaseProductLine, ...]  # worst profit first, empty returns last


def base_product_detail(report: ProfitReport, maps: Iterable[ListingMap], name: str) -> BaseProductDetail:
    """Same scope as ProfitReport.by_base_product: only orders whose COGS is fully known."""
    units = {m.sku: m.units_per_listing for m in maps if m.base_product == name}
    acc: dict[str, list] = {sku: [set(), 0, 0, 0, 0] for sku in units}
    lines: list[BaseProductLine] = []
    for o in report.orders:
        if o.cogs is None:
            continue
        for ln in o.lines:
            if ln.sku not in units:
                continue
            cogs = ln.cogs or 0
            lines.append(BaseProductLine(o.settled_at, o.platform, o.order_id, ln.sku, ln.quantity, units[ln.sku], ln.net_received, cogs, ln.allocated_expense))
            a = acc[ln.sku]
            a[0].add(o.order_id)
            a[1] += ln.quantity
            a[2] += ln.net_received
            a[3] += cogs
            a[4] += ln.allocated_expense
    listings = [ListingBreakdown(sku, units[sku], len(a[0]), a[1], a[2], a[3], a[4]) for sku, a in acc.items()]
    listings.sort(key=lambda r: (r.order_count == 0, r.net_profit, r.sku))
    lines.sort(key=lambda ln: (ln.empty_return, ln.profit, ln.order_id))
    return BaseProductDetail(name, tuple(listings), tuple(lines))
