"""Use case: TikTok PriceSimulation (ADR-0008) — learn fee rates from recent real Settlements, then simulate."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.domain.pricing import (
    FeeRates,
    LearnedRates,
    PriceBreakdown,
    PriceScenario,
    learn_fee_rates,
    min_list_price,
    simulate,
)
from app.domain.profit import effective_cost
from app.domain.types import ExpenseKind, Platform
from app.effects import db
from app.orchestration.profit_report import BuildProfitReport

LEARN_DAYS = 60
COMPARE_DISCOUNTS_BP = (0, 1000, 2000, 3000, 4000, 5000)


@dataclass(frozen=True)
class PricingRequest:
    base_product: str = ""
    units: int = 1
    list_price: int | None = None
    shop_discount_bp: int = 0
    shop_coupon: int = 0
    platform_discount_bp: int = 0
    affiliate_bp: int = 0
    target_profit: int = 0
    rate_overrides: dict[str, int] = field(default_factory=dict)  # FeeRates field → value


@dataclass(frozen=True)
class CompareRow:
    shop_discount_bp: int
    break_even: PriceBreakdown | None
    target: PriceBreakdown | None


@dataclass(frozen=True)
class PricingResult:
    learned: LearnedRates
    learned_from: date
    learned_to: date
    rates: FeeRates
    base_products: list  # BaseProductRow
    unit_cost: int | None
    basket_cost: int | None
    breakdown: PriceBreakdown | None  # at the full price typed in, else at the target price
    breakdown_is_target: bool
    break_even: PriceBreakdown | None  # at the lowest full price with profit ≥ 0
    target: PriceBreakdown | None  # at the lowest full price with profit ≥ target
    compare: tuple[CompareRow, ...]


class SimulatePrice:
    def __init__(self, session: Session):
        self.s = session

    def run(self, req: PricingRequest, *, today: date) -> PricingResult:
        start = today - timedelta(days=LEARN_DAYS - 1)
        settlements = [x for x in db.settlements_between(self.s, start, today) if x.platform is Platform.TIKTOK]
        # expense share exactly as the profit page allocates it (all platforms visible, ADR-0002)
        pnl = BuildProfitReport(self.s).run(start=start, end=today).by_platform.get(Platform.TIKTOK.value)
        learned = learn_fee_rates(settlements, pnl.expense_total if pnl else 0, pnl.expenses.get(ExpenseKind.ADS, 0) if pnl else 0)
        rates = replace(learned.rates, **req.rate_overrides)
        unit_cost = effective_cost(db.all_sku_costs(self.s), req.base_product, today) if req.base_product else None
        breakdown = break_even = target = None
        compare: tuple[CompareRow, ...] = ()
        is_target = False
        if unit_cost is not None:
            common = dict(shop_coupon=req.shop_coupon, unit_cost=unit_cost, units=req.units, affiliate_bp=req.affiliate_bp,
                          platform_discount_bp=req.platform_discount_bp)

            def at(price: int | None, discount_bp: int) -> PriceBreakdown | None:
                return None if price is None else simulate(PriceScenario(list_price=price, shop_discount_bp=discount_bp, **common), rates)

            def lowest(profit: int, discount_bp: int) -> PriceBreakdown | None:
                return at(min_list_price(profit, rates, shop_discount_bp=discount_bp, **common), discount_bp)

            break_even, target = lowest(0, req.shop_discount_bp), lowest(req.target_profit, req.shop_discount_bp)
            breakdown = at(req.list_price, req.shop_discount_bp) if req.list_price else target
            is_target = not req.list_price and target is not None
            compare = tuple(CompareRow(d, lowest(0, d), lowest(req.target_profit, d)) for d in COMPARE_DISCOUNTS_BP)
        basket_cost = None if unit_cost is None else unit_cost * req.units
        return PricingResult(learned, start, today, rates, db.list_base_products(self.s), unit_cost, basket_cost, breakdown, is_target,
                             break_even, target, compare)
