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
    ads_spend,
    learn_fee_rates,
    min_list_price,
    simulate,
)
from app.domain.profit import effective_cost
from app.domain.types import Platform
from app.effects import db

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
    break_even_price: int | None
    target_price: int | None


@dataclass(frozen=True)
class PricingResult:
    learned: LearnedRates
    learned_from: date
    learned_to: date
    rates: FeeRates
    base_products: list  # BaseProductRow
    unit_cost: int | None
    basket_cost: int | None
    breakdown: PriceBreakdown | None
    break_even_price: int | None
    target_price: int | None
    compare: tuple[CompareRow, ...]


class SimulatePrice:
    def __init__(self, session: Session):
        self.s = session

    def run(self, req: PricingRequest, *, today: date) -> PricingResult:
        start = today - timedelta(days=LEARN_DAYS - 1)
        settlements = [x for x in db.settlements_between(self.s, start, today) if x.platform is Platform.TIKTOK]
        learned = learn_fee_rates(settlements, ads_spend(db.all_expenses(self.s), Platform.TIKTOK.value, start, today))
        rates = replace(learned.rates, **req.rate_overrides)
        unit_cost = effective_cost(db.all_sku_costs(self.s), req.base_product, today) if req.base_product else None
        breakdown = break_even = target = None
        compare: tuple[CompareRow, ...] = ()
        if unit_cost is not None:
            common = dict(shop_coupon=req.shop_coupon, unit_cost=unit_cost, units=req.units, affiliate_bp=req.affiliate_bp,
                          platform_discount_bp=req.platform_discount_bp)
            if req.list_price:
                breakdown = simulate(PriceScenario(list_price=req.list_price, shop_discount_bp=req.shop_discount_bp, **common), rates)
            break_even = min_list_price(0, rates, shop_discount_bp=req.shop_discount_bp, **common)
            target = min_list_price(req.target_profit, rates, shop_discount_bp=req.shop_discount_bp, **common)
            compare = tuple(CompareRow(d, min_list_price(0, rates, shop_discount_bp=d, **common),
                                       min_list_price(req.target_profit, rates, shop_discount_bp=d, **common)) for d in COMPARE_DISCOUNTS_BP)
        basket_cost = None if unit_cost is None else unit_cost * req.units
        return PricingResult(learned, start, today, rates, db.list_base_products(self.s), unit_cost, basket_cost, breakdown, break_even, target, compare)
