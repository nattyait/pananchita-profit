"""Profit engine (pure). Builds ProfitReport from Settlement, OrderLine, SkuCost, Expense.

Trust Invariant: revenue comes ONLY from Settlement.net_received. OrderLine is used for COGS only.
This module never branches on a platform name.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.domain.allocation import split_proportionally
from app.domain.dates import in_period
from app.domain.types import SHARED, Expense, ExpenseKind, ImportProblem, ListingMap, OrderLine, Platform, Settlement, SkuCost


@dataclass(frozen=True)
class OrderLineProfit:
    """One product line's share of an order (ADR-0004)."""

    sku: str
    product_name: str
    quantity: int
    net_received: int  # share of the order's Settlement
    cogs: int | None
    allocated_expense: int  # share

    @property
    def contribution(self) -> int | None:
        return None if self.cogs is None else self.net_received - self.cogs

    @property
    def profit(self) -> int | None:
        return None if self.cogs is None else self.net_received - self.cogs - self.allocated_expense


@dataclass(frozen=True)
class OrderProfit:
    platform: Platform
    order_id: str
    settled_at: date
    ordered_at: date | None
    net_received: int
    cogs: int | None  # None when any SKU cost is unknown → problem, not zero
    allocated_expense: int
    fee_total: int
    quantity: int
    lines: tuple[OrderLineProfit, ...] = ()

    @property
    def fully_returned(self) -> bool:
        """Order lines exist but every piece came back (quantity after returns is 0)."""
        return bool(self.lines) and self.quantity == 0

    @property
    def empty_return(self) -> bool:
        """Fully returned and the platform moved no money for it: nothing to show but the fact."""
        return self.fully_returned and self.net_received == 0 and self.fee_total == 0

    @property
    def contribution(self) -> int | None:
        return None if self.cogs is None else self.net_received - self.cogs

    @property
    def profit(self) -> int | None:
        c = self.contribution
        return None if c is None else c - self.allocated_expense


@dataclass(frozen=True)
class PendingOrder:
    platform: Platform
    order_id: str
    ordered_at: date
    status: str
    payment_method: str
    quantity: int


@dataclass(frozen=True)
class PeriodPnl:
    platform: str  # Platform value or "all"
    order_count: int
    net_received: int
    cogs: int
    expenses: dict[ExpenseKind, int]
    cogs_incomplete_orders: int = 0

    @property
    def expense_total(self) -> int:
        return sum(self.expenses.values())

    @property
    def contribution(self) -> int:
        return self.net_received - self.cogs

    @property
    def net_profit(self) -> int:
        return self.contribution - self.expense_total


@dataclass(frozen=True)
class ProductPnl:
    sku: str
    product_name: str
    order_count: int
    quantity: int
    net_received: int
    cogs: int
    expense: int

    @property
    def contribution(self) -> int:
        return self.net_received - self.cogs

    @property
    def net_profit(self) -> int:
        return self.net_received - self.cogs - self.expense


@dataclass(frozen=True)
class ProfitReport:
    period_start: date
    period_end: date
    by_platform: dict[str, PeriodPnl]
    total: PeriodPnl
    orders: tuple[OrderProfit, ...]
    pending: tuple[PendingOrder, ...]
    problems: tuple[ImportProblem, ...] = field(default_factory=tuple)
    by_product: dict[str, ProductPnl] = field(default_factory=dict)
    by_base_product: dict[str, ProductPnl] = field(default_factory=dict)  # quantity = base units (ADR-0006)


def effective_cost(costs: tuple[SkuCost, ...], sku: str, on: date) -> int | None:
    candidates = [c for c in costs if c.sku == sku and c.effective_from <= on]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.effective_from).unit_cost


def effective_unit_cost(costs: tuple[SkuCost, ...], maps: dict[str, ListingMap], sku: str, on: date) -> int | None:
    """Cost of ONE sold piece of a listing (ADR-0006): via its BaseProduct × units, else the ProductKey's own cost."""
    m = maps.get(sku)
    if m is not None:
        base = effective_cost(costs, m.base_product, on)
        return None if base is None else base * m.units_per_listing
    return effective_cost(costs, sku, on)


def cogs_for(lines: tuple[OrderLine, ...], costs: tuple[SkuCost, ...], maps: dict[str, ListingMap] | None = None) -> tuple[int | None, tuple[ImportProblem, ...]]:
    """Σ quantity × unit cost effective on ordered_at. Any unknown cost → (None, problems)."""
    maps = maps or {}
    total = 0
    problems: list[ImportProblem] = []
    for line in lines:
        unit = effective_unit_cost(costs, maps, line.sku, line.ordered_at)
        if unit is None:
            m = maps.get(line.sku)
            what = f"สินค้าฐาน {m.base_product}" if m else f"รายการ {line.sku}"
            field, key = ("base_product", m.base_product) if m else ("sku", line.sku)
            problems.append(ImportProblem(f"ไม่มีต้นทุนของ{what} ณ วันที่ {line.ordered_at:%d/%m/%Y}", None, field, key))
            continue
        total += unit * line.quantity
    return (None if problems else total, tuple(problems))


def split_order_lines(lines: tuple[OrderLine, ...], net_received: int, allocated_expense: int, costs: tuple[SkuCost, ...],
                      maps: dict[str, ListingMap] | None = None) -> tuple[OrderLineProfit, ...]:
    """ADR-0004: weights = line_amount, else quantity, else equal (e.g. fully returned lines). Shares sum exactly to the order figures."""
    weights = {i: ln.line_amount for i, ln in enumerate(lines)}
    if not any(w > 0 for w in weights.values()):
        weights = {i: ln.quantity for i, ln in enumerate(lines)}
    if not any(w > 0 for w in weights.values()):
        weights = {i: 1 for i, _ in enumerate(lines)}
    net_share = split_proportionally(net_received, weights)
    exp_share = split_proportionally(allocated_expense, weights)
    out = []
    for i, ln in enumerate(lines):
        unit = effective_unit_cost(costs, maps or {}, ln.sku, ln.ordered_at)
        out.append(OrderLineProfit(ln.sku, ln.product_name, ln.quantity, net_share.get(i, 0), None if unit is None else unit * ln.quantity, exp_share.get(i, 0)))
    return tuple(out)


def _fee_total(s: Settlement) -> int:
    return s.commission_fee + s.service_fee + s.transaction_fee + s.affiliate_fee + s.tax_fee + s.platform_fee + s.ads_fee + s.shipping_fee_diff + s.other_adjustment


def build_report(
    *,
    period_start: date,
    period_end: date,
    settlements: tuple[Settlement, ...],
    order_lines: tuple[OrderLine, ...],
    sku_costs: tuple[SkuCost, ...],
    expenses: tuple[Expense, ...],
    platform: Platform | None = None,
    listing_maps: tuple[ListingMap, ...] = (),
) -> ProfitReport:
    maps = {m.sku: m for m in listing_maps}
    settled_any_platform = [s for s in settlements if in_period(s.settled_at, period_start, period_end)]
    settled = [s for s in settled_any_platform if platform is None or s.platform == platform]
    period_expenses = [e for e in expenses if in_period(e.incurred_on, period_start, period_end)]
    lines_by_order: dict[tuple[str, str], list[OrderLine]] = defaultdict(list)
    for ln in order_lines:
        if platform is None or ln.platform == platform:
            lines_by_order[(ln.platform.value, ln.order_id)].append(ln)

    # --- per platform net_received (weights for allocation) ---
    net_by_platform: dict[str, int] = defaultdict(int)
    for s in settled:
        net_by_platform[s.platform.value] += s.net_received
    platforms_present = list(net_by_platform) or ([platform.value] if platform else [])
    # shared expense is split across ALL platforms, so a filtered view shows the same share as the "all" view
    net_all_platforms: dict[str, int] = defaultdict(int)
    for s in settled_any_platform:
        net_all_platforms[s.platform.value] += s.net_received

    # --- expenses → platform (ADR-0002) ---
    exp_by_platform: dict[str, dict[ExpenseKind, int]] = {p: defaultdict(int) for p in platforms_present}
    unallocated_shared: dict[ExpenseKind, int] = defaultdict(int)
    for e in period_expenses:
        if e.platform == SHARED:
            shares = split_proportionally(e.amount, dict(net_all_platforms))
            if not shares:
                unallocated_shared[e.kind] += e.amount
            for p, amt in shares.items():
                if platform is None or p == platform.value:
                    exp_by_platform.setdefault(p, defaultdict(int))[e.kind] += amt
        elif platform is None or e.platform == platform.value:
            exp_by_platform.setdefault(e.platform, defaultdict(int))[e.kind] += e.amount

    # --- expenses → each Settlement within platform, by its own net_received (an order paid twice is not charged twice) ---
    alloc: dict[tuple[str, str, date], int] = {}
    for p, kinds in exp_by_platform.items():
        weights = {s.settlement_key: s.net_received for s in settled if s.platform.value == p}
        alloc.update(split_proportionally(sum(kinds.values()), weights))

    # --- OrderProfit ---
    orders: list[OrderProfit] = []
    problems: list[ImportProblem] = []
    cogs_by_platform: dict[str, int] = defaultdict(int)
    incomplete_by_platform: dict[str, int] = defaultdict(int)
    count_by_platform: dict[str, int] = defaultdict(int)
    for s in settled:
        key = (s.platform.value, s.order_id)
        lines = tuple(lines_by_order.get(key, ()))
        if lines:
            cogs, probs = cogs_for(lines, sku_costs, maps)
        else:
            cogs, probs = None, (ImportProblem(f"ออเดอร์ {s.order_id} ยังไม่มีรายการสินค้า (อัพโหลดรายงานคำสั่งซื้อ)", None, "order_id"),)
        problems.extend(probs)
        count_by_platform[s.platform.value] += 1
        if cogs is None:
            incomplete_by_platform[s.platform.value] += 1
        else:
            cogs_by_platform[s.platform.value] += cogs
        orders.append(
            OrderProfit(
                platform=s.platform, order_id=s.order_id, settled_at=s.settled_at,
                ordered_at=min(ln.ordered_at for ln in lines) if lines else None,
                net_received=s.net_received, cogs=cogs,
                allocated_expense=alloc.get(s.settlement_key, 0), fee_total=_fee_total(s),
                quantity=sum(ln.quantity for ln in lines),
                lines=split_order_lines(lines, s.net_received, alloc.get(s.settlement_key, 0), sku_costs, maps),
            )
        )

    # --- PendingOrder: live (not cancelled) order lines with no settlement at all (any date) ---
    settled_keys = {(s.platform.value, s.order_id) for s in settlements}
    pending: list[PendingOrder] = []
    for key, all_lines in lines_by_order.items():
        lines = [ln for ln in all_lines if not ln.cancelled]
        if key in settled_keys or not lines:
            continue
        first = lines[0]
        pending.append(PendingOrder(first.platform, first.order_id, min(ln.ordered_at for ln in lines), first.status, first.payment_method, sum(ln.quantity for ln in lines)))

    # --- ProductPnl: only lines whose profit is known (ADR-0004) ---
    prod: dict[str, list] = {}
    for o in orders:
        if o.cogs is None:
            continue
        for ln in o.lines:
            acc = prod.setdefault(ln.sku, [ln.product_name, set(), 0, 0, 0, 0])
            acc[1].add(o.order_id)
            acc[2] += ln.quantity
            acc[3] += ln.net_received
            acc[4] += ln.cogs or 0
            acc[5] += ln.allocated_expense
    by_product = {sku: ProductPnl(sku, a[0], len(a[1]), a[2], a[3], a[4], a[5]) for sku, a in prod.items()}
    # --- per BaseProduct: quantity in base units (ADR-0006) ---
    base: dict[str, list] = {}
    for o in orders:
        if o.cogs is None:
            continue
        for ln in o.lines:
            m = maps.get(ln.sku)
            if m is None:
                continue
            acc = base.setdefault(m.base_product, [m.base_product, set(), 0, 0, 0, 0])
            acc[1].add(o.order_id)
            acc[2] += ln.quantity * m.units_per_listing
            acc[3] += ln.net_received
            acc[4] += ln.cogs or 0
            acc[5] += ln.allocated_expense
    by_base_product = {n: ProductPnl(n, a[0], len(a[1]), a[2], a[3], a[4], a[5]) for n, a in base.items()}

    by_platform = {
        p: PeriodPnl(p, count_by_platform[p], net_by_platform[p], cogs_by_platform[p], dict(exp_by_platform.get(p, {})), incomplete_by_platform[p])
        for p in sorted(set(platforms_present) | set(exp_by_platform))
    }
    total_exp: dict[ExpenseKind, int] = defaultdict(int)
    for kinds in exp_by_platform.values():
        for k, v in kinds.items():
            total_exp[k] += v
    for k, v in unallocated_shared.items():
        total_exp[k] += v
    total = PeriodPnl(
        "all", sum(count_by_platform.values()), sum(net_by_platform.values()), sum(cogs_by_platform.values()),
        dict(total_exp), sum(incomplete_by_platform.values()),
    )
    return ProfitReport(
        period_start, period_end, by_platform, total,
        tuple(sorted(orders, key=lambda o: (o.settled_at, o.order_id), reverse=True)),
        tuple(sorted(pending, key=lambda p: p.ordered_at, reverse=True)),
        tuple(problems),
        dict(sorted(by_product.items(), key=lambda kv: kv[1].net_profit, reverse=True)),
        dict(sorted(by_base_product.items(), key=lambda kv: kv[1].net_profit, reverse=True)),
    )
