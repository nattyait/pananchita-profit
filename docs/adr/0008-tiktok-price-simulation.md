# ADR-0008: PriceSimulation — what-if pricing for TikTok baskets, fee rates learned from real Settlements

Status: Accepted · Date: 2026-09-29

## Context
TikTok profit was thin because full prices were set without knowing what is left after campaign discounts, TikTok
fees, affiliate commission and ads. The shop must join campaigns (a listing without a visible discount gets no clicks),
often funding the discount/coupon itself. The owner wants: "at this full price and this discount, what is left?" and
"what is the lowest full price that still does not lose money (or makes X per basket)?"

Real TikTok income rows (tests/fixtures_tiktok_real.py) show every fee is charged on the price **after the shop's own
discount/coupon** (`ยอดรวมค่าสินค้าหลังหักส่วนลดจากผู้ขาย`); a discount TikTok funds changes what the customer pays, not
what the shop is charged or receives. Rates seen: commission 10.70 %, order fee 3.21 %, growth-support fee 8.03 %,
infrastructure fee 1.07 baht per order, LIVE coupon service fee 4.28 % when joined.

## Decision
1. New page `/pricing` ("ตั้งราคา TikTok"). A **PriceSimulation** is pure (`domain/pricing.py`):
   `after = full − full × shop% − shop coupon`; each fee = rate × after; `net_received = after − fees − fixed`;
   `COGS = units × SkuCost of the BaseProduct today`; `ads = ads% × net_received`; `profit = net_received − COGS − ads`.
2. `min_list_price(target)` returns the lowest whole-baht full price whose simulated profit ≥ target (solved exactly
   with fractions, then checked with the same rounding as `simulate`); None when deductions reach 100 %.
3. **FeeRates are learned, editable**: averages over TikTok Settlements of the last 60 days with product_price > 0
   (`learn_fee_rates`): commission, order fee, "other service" (= service_fee + shipping the shop paid: growth support
   + coupon/campaign service fees on average), fixed = average platform_fee per order, ads = TikTok ads Expense ÷
   TikTok net_received in the window. Affiliate % is an input (default 0); the observed average among orders that
   paid an affiliate is shown as a hint. Any rate can be overridden on the page for the current simulation only.
4. A simulation is never stored and never feeds ProfitReport; the cash-basis Trust Invariants are untouched.

## Consequences
- (+) Prices are set from the shop's real deductions, not guesses; campaign fee changes show up in the learned rates.
- (−) "Other service" is an average: a campaign the shop rarely joins is under-represented — the page says to add its
  fee (e.g. 4.28 %) by hand.
- (−) Assumes fees are proportional to the post-discount price plus one fixed amount; true for the observed rows.
- New terms in CONTEXT.md: PriceSimulation, FeeRates.
