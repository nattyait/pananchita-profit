"""PriceSimulation (pure, ADR-0008): what a basket leaves the shop at a given full price and discount, and the lowest
full price that still meets a profit target. A what-if tool: it never feeds the cash-basis profit report.

TikTok charges its fees on the price after the SHOP's own discount/coupon; a discount TikTok funds does not change
what the shop is charged or receives (seen in the real income rows, ADR-0008).
Rates are basis points (1070 = 10.70 %), money is satang.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from math import ceil

from app.domain.types import Settlement


@dataclass(frozen=True)
class FeeRates:
    commission_bp: int
    transaction_bp: int
    service_bp: int  # growth-support + campaign/coupon service fees + shipping the shop pays, as seen on average
    fixed_per_order: int  # satang, e.g. infrastructure fee
    expense_bp: int  # every Expense of the platform (own + its ADR-0002 share of shared) as a share of net_received


@dataclass(frozen=True)
class PriceScenario:
    list_price: int  # full price of one sold piece (the basket), satang
    shop_discount_bp: int
    shop_coupon: int  # satang, on top of the % discount
    unit_cost: int  # SkuCost of one base unit, satang
    units: int  # base units in the basket (units_per_listing)
    affiliate_bp: int
    platform_discount_bp: int  # funded by the platform: changes what the customer pays, not what the shop gets


@dataclass(frozen=True)
class PriceBreakdown:
    list_price: int
    after_shop_discount: int
    customer_pays: int
    commission: int
    transaction: int
    service: int
    affiliate: int
    fixed: int
    net_received: int
    cogs: int
    expense: int  # share of Expense (ads + other + shared), as on the profit page

    @property
    def fees(self) -> int:
        return self.commission + self.transaction + self.service + self.affiliate + self.fixed

    @property
    def contribution(self) -> int:
        return self.net_received - self.cogs

    @property
    def profit(self) -> int:
        return self.contribution - self.expense

    @property
    def shop_discount_total(self) -> int:
        return self.list_price - self.after_shop_discount

    @property
    def margin_bp(self) -> int:
        """Profit as a share of the full price."""
        return self.profit * 10000 // self.list_price if self.list_price else 0


def _pct(amount: int, bp: int) -> int:
    return int((Decimal(amount) * bp / 10000).quantize(Decimal("1"), ROUND_HALF_UP))


def simulate(s: PriceScenario, rates: FeeRates) -> PriceBreakdown:
    after = s.list_price - _pct(s.list_price, s.shop_discount_bp) - s.shop_coupon
    commission, transaction, service = _pct(after, rates.commission_bp), _pct(after, rates.transaction_bp), _pct(after, rates.service_bp)
    affiliate = _pct(after, s.affiliate_bp)
    net = after - commission - transaction - service - affiliate - rates.fixed_per_order
    return PriceBreakdown(s.list_price, after, after - _pct(after, s.platform_discount_bp), commission, transaction, service, affiliate,
                          rates.fixed_per_order, net, s.unit_cost * s.units, _pct(net, rates.expense_bp))


def min_list_price(target_profit: int, rates: FeeRates, **scenario: int) -> int | None:
    """Lowest full price in whole baht whose simulated profit ≥ target_profit; None if deductions ≥ 100 %."""
    pct = rates.commission_bp + rates.transaction_bp + rates.service_bp + scenario["affiliate_bp"]
    if pct >= 10000 or rates.expense_bp >= 10000 or scenario["shop_discount_bp"] >= 10000:
        return None
    cogs = scenario["unit_cost"] * scenario["units"]
    net_needed = Fraction(target_profit + cogs) / (1 - Fraction(rates.expense_bp, 10000))
    after_needed = (net_needed + rates.fixed_per_order) / (1 - Fraction(pct, 10000))
    price = ceil((after_needed + scenario["shop_coupon"]) / (1 - Fraction(scenario["shop_discount_bp"], 10000)) / 100) * 100
    price = max(price - 200, 0)  # step up from just below to absorb per-fee rounding
    while simulate(PriceScenario(list_price=price, **scenario), rates).profit < target_profit:
        price += 100
    return price


@dataclass(frozen=True)
class LearnedRates:
    rates: FeeRates
    orders: int  # settlements used as samples
    affiliate_bp: int  # average commission among orders that paid an affiliate
    affiliate_orders: int
    ads_bp: int  # the ads part of expense_bp, shown for information

    @property
    def other_expense_bp(self) -> int:
        """expense_bp minus its ads part: other platform Expense + the share of shared Expense."""
        return self.rates.expense_bp - self.ads_bp


def learn_fee_rates(settlements: Iterable[Settlement], expense_total: int, ads_total: int = 0) -> LearnedRates:
    """Average rates from real Settlements (fees are negative in the report) as a share of product_price.
    expense_total / ads_total: the platform's Expense in the same window as the profit page allocates it (ADR-0002)."""
    ss = list(settlements)
    sample = [s for s in ss if s.product_price > 0]
    base = sum(s.product_price for s in sample)

    def rate(total: int, over: int) -> int:
        return max(0, round(-total / over * 10000)) if over > 0 else 0

    with_aff = [s for s in sample if s.affiliate_fee < 0]
    net_all = sum(s.net_received for s in ss)
    rates = FeeRates(
        commission_bp=rate(sum(s.commission_fee for s in sample), base),
        transaction_bp=rate(sum(s.transaction_fee for s in sample), base),
        service_bp=rate(sum(s.service_fee + s.shipping_fee_diff for s in sample), base),
        fixed_per_order=max(0, round(-sum(s.platform_fee for s in sample) / len(sample))) if sample else 0,
        expense_bp=max(0, round(expense_total / net_all * 10000)) if net_all > 0 else 0,
    )
    return LearnedRates(rates, len(sample), rate(sum(s.affiliate_fee for s in with_aff), sum(s.product_price for s in with_aff)), len(with_aff),
                        max(0, round(ads_total / net_all * 10000)) if net_all > 0 else 0)

