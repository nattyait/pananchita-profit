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
    def contribution(self) -> int:
        return self.net_received - self.cogs

    @property
    def net_profit(self) -> int:
        return self.net_received - self.cogs - self.expense

    @property
    def suspicious(self) -> bool:
        return self.units_per_listing > SUSPICIOUS_UNITS


@dataclass(frozen=True)
class BaseProductOrder:
    """One order's lines of this BaseProduct, summed over all its Settlements in the period
    (e.g. paid on one day, clawed back after a return on another)."""

    platform: Platform
    order_id: str
    skus: tuple[str, ...]
    units_per_listing: tuple[int, ...]  # aligned with skus
    first_settled_at: date
    last_settled_at: date
    settlement_count: int
    pieces: int
    received: int  # sum of positive shares
    clawed_back: int  # sum of negative shares (≤ 0)
    cogs: int
    expense: int

    @property
    def net_received(self) -> int:
        return self.received + self.clawed_back

    @property
    def contribution(self) -> int:
        return self.net_received - self.cogs

    @property
    def profit(self) -> int:
        return self.net_received - self.cogs - self.expense

    @property
    def fully_returned(self) -> bool:
        return self.pieces == 0

    @property
    def empty_return(self) -> bool:
        """Every piece came back and no money moved for it in the period."""
        return self.pieces == 0 and self.received == 0 and self.clawed_back == 0 and self.expense == 0


@dataclass(frozen=True)
class BaseProductDetail:
    name: str
    listings: tuple[ListingBreakdown, ...]  # sold ones worst net_profit first, then unsold
    orders: tuple[BaseProductOrder, ...]  # worst profit first, empty returns last


def base_product_detail(report: ProfitReport, maps: Iterable[ListingMap], name: str) -> BaseProductDetail:
    """Same scope as ProfitReport.by_base_product: only Settlements whose COGS is fully known."""
    units = {m.sku: m.units_per_listing for m in maps if m.base_product == name}
    acc: dict[str, list] = {sku: [set(), 0, 0, 0, 0] for sku in units}
    by_order: dict[tuple[Platform, str], dict] = {}
    for o in report.orders:
        if o.cogs is None:
            continue
        mine = [ln for ln in o.lines if ln.sku in units]
        if not mine:
            continue
        g = by_order.setdefault((o.platform, o.order_id), {"dates": [], "pieces": {}, "received": 0, "clawed_back": 0, "cogs": 0, "expense": 0})
        g["dates"].append(o.settled_at)
        for ln in mine:
            g["pieces"][ln.sku] = ln.quantity  # the same lines repeat on every Settlement of the order
            g["received" if ln.net_received >= 0 else "clawed_back"] += ln.net_received
            g["cogs"] += ln.cogs or 0
            g["expense"] += ln.allocated_expense
            a = acc[ln.sku]
            a[0].add(o.order_id)
            a[2] += ln.net_received
            a[3] += ln.cogs or 0
            a[4] += ln.allocated_expense
    for (_, _), g in by_order.items():
        for sku, q in g["pieces"].items():
            acc[sku][1] += q
    orders = [
        BaseProductOrder(platform, order_id, tuple(g["pieces"]), tuple(units[k] for k in g["pieces"]), min(g["dates"]), max(g["dates"]),
                         len(g["dates"]), sum(g["pieces"].values()), g["received"], g["clawed_back"], g["cogs"], g["expense"])
        for (platform, order_id), g in by_order.items()
    ]
    orders.sort(key=lambda r: (r.empty_return, r.profit, r.order_id))
    listings = [ListingBreakdown(sku, units[sku], len(a[0]), a[1], a[2], a[3], a[4]) for sku, a in acc.items()]
    listings.sort(key=lambda r: (r.order_count == 0, r.net_profit, r.sku))
    return BaseProductDetail(name, tuple(listings), tuple(orders))
