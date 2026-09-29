"""PriceSimulation spec (ADR-0008). Rates are basis points (1070 = 10.70%), money is satang."""
from datetime import date

import pytest

from app.domain.money import parse_percent_bp
from app.domain.pricing import FeeRates, PriceScenario, learn_fee_rates, min_list_price, simulate
from app.domain.types import Platform, Settlement

# rates seen on the real TikTok income rows (fixtures_tiktok_real.py)
REAL = FeeRates(commission_bp=1070, transaction_bp=321, service_bp=803, fixed_per_order=107, ads_bp=0)


def test_simulate_reproduces_a_real_tiktok_order():
    # full 1,380.00, shop coupon 165.67 → fees charged on 1,214.33; TikTok's own discount does not change what the shop gets
    s = PriceScenario(list_price=138000, shop_discount_bp=0, shop_coupon=16567, unit_cost=0, units=1, affiliate_bp=0, platform_discount_bp=2600)
    b = simulate(s, REAL)
    assert b.after_shop_discount == 121433
    assert b.commission == 12993 and b.transaction == 3898 and b.service == 9751 and b.fixed == 107
    assert b.net_received == 121433 - 12993 - 3898 - 9751 - 107
    assert b.customer_pays == 121433 - 31573  # 26% of 1,214.33 paid by TikTok, shown for info only


def test_profit_after_cogs_affiliate_and_ads():
    rates = FeeRates(commission_bp=1070, transaction_bp=321, service_bp=803, fixed_per_order=107, ads_bp=1200)
    s = PriceScenario(list_price=100000, shop_discount_bp=4000, shop_coupon=0, unit_cost=11000, units=5, affiliate_bp=1000, platform_discount_bp=0)
    b = simulate(s, rates)
    assert b.after_shop_discount == 60000
    assert b.affiliate == 6000
    fees = 6420 + 1926 + 4818 + 6000 + 107
    assert b.net_received == 60000 - fees
    assert b.cogs == 55000
    assert b.contribution == b.net_received - 55000
    assert b.ads == (60000 - fees) * 1200 // 10000
    assert b.profit == b.contribution - b.ads < 0


def test_min_list_price_is_the_lowest_whole_baht_meeting_the_target():
    rates = FeeRates(commission_bp=1070, transaction_bp=321, service_bp=803, fixed_per_order=107, ads_bp=1200)
    base = dict(shop_discount_bp=4000, shop_coupon=2000, unit_cost=11000, units=5, affiliate_bp=1000, platform_discount_bp=0)
    for target in (0, 5000):
        price = min_list_price(target, rates, **base)
        assert price % 100 == 0
        assert simulate(PriceScenario(list_price=price, **base), rates).profit >= target
        assert simulate(PriceScenario(list_price=price - 100, **base), rates).profit < target


def test_min_list_price_is_none_when_deductions_take_everything():
    rates = FeeRates(commission_bp=5000, transaction_bp=3000, service_bp=2000, fixed_per_order=0, ads_bp=0)
    assert min_list_price(0, rates, shop_discount_bp=0, shop_coupon=0, unit_cost=100, units=1, affiliate_bp=0, platform_discount_bp=0) is None


def test_learn_rates_from_real_settlements():
    d = date(2026, 9, 10)
    settlements = [
        Settlement(Platform.TIKTOK, "A", d, 89487, product_price=121433, commission_fee=-12993, transaction_fee=-3898, service_fee=-14948,
                   platform_fee=-107),
        Settlement(Platform.TIKTOK, "B", d, 41342, product_price=53100, commission_fee=-5682, transaction_fee=-1705, service_fee=-4264,
                   platform_fee=-107, affiliate_fee=-5310),
        Settlement(Platform.TIKTOK, "R", d, -86004),  # clawback: no product_price → not a sample
    ]
    learned = learn_fee_rates(settlements, ads_total=13000)
    assert learned.orders == 2
    assert learned.rates.commission_bp == 1070 and learned.rates.transaction_bp == 321
    assert learned.rates.service_bp == round((14948 + 4264) / (121433 + 53100) * 10000)
    assert learned.rates.fixed_per_order == 107
    assert learned.affiliate_bp == 1000 and learned.affiliate_orders == 1  # average among orders that had an affiliate
    assert learned.rates.ads_bp == round(13000 / (89487 + 41342 - 86004) * 10000)


@pytest.mark.parametrize("text, bp", [("10.7", 1070), ("8.03", 803), ("40", 4000), ("0", 0), (" 12.5 % ", 1250)])
def test_parse_percent_bp(text, bp):
    assert parse_percent_bp(text) == bp
