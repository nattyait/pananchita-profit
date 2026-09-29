# ADR-0007: ReportKind `ads` — TikTok Ads Manager statement imports only ad bills paid outside the payout

Status: Accepted · Date: 2026-09-29

## Context
ร้านจ่ายค่าโฆษณา TikTok สองทาง:
1. **GMV Pay** — TikTok หักจากยอดโอนของร้าน รายการนี้อยู่ในรายงานรายรับ ("การชำระเงินด้วย GMV สำหรับโฆษณา TikTok")
   และถูกนำเข้าเป็น Expense อัตโนมัติแล้ว (ADR-0005)
2. **บัตรเครดิต/เดบิต** — ร้านจ่ายเอง ไม่ผ่านยอดโอน จึงไม่มีในรายงานใด ๆ ที่ระบบรับ → ค่าแอดขาด กำไรสูงเกินจริง

ใบแจ้งยอดจาก TikTok Ads Manager (`Transaction_<account id>_<เวลา>.xlsx`) มีทั้งสองแบบปนกัน พร้อมแถว "Ad credit"
(เครดิตฟรีจาก TikTok) ถ้านำเข้าทั้งไฟล์ ค่าแอด GMV Pay จะถูกนับซ้ำ

## Decision
1. เพิ่ม ReportKind `ads` (ใบแจ้งยอดค่าโฆษณา) — สร้างแค่ Expense (kind `ads`) ไม่สร้าง Settlement หรือ OrderLine
2. Parser `tiktok.parse_ads` ขับด้วย yaml (`config/platforms/tiktok.yaml` › `reports.ads.options`):
   - `free_fund_types` (Ad credit) → ข้าม
   - `success_statuses` ไม่ตรง / `charge_subtypes` ไม่ตรง → ImportProblem
   - วิธีจ่ายอ่านจาก Description หลัง "Payment method:"
     - อยู่ใน `payout_payment_methods` (GMV Pay) → ข้าม เพราะนำเข้าจากรายงานรายรับแล้ว
     - อยู่ใน `charged_payment_methods` (Credit or debit card) → Expense
     - วิธีอื่นที่ไม่รู้จัก → ImportProblem **ไม่เดา** (เดาผิดทางหนึ่งได้ค่าแอดซ้ำ อีกทางค่าแอดหาย)
   - แถวที่ข้ามรายงานเป็นจำนวนรวมใน problems ของ upload เสมอ ไม่ข้ามเงียบ
3. กันซ้ำด้วย `source_ref = "tiktok-ads:<Transaction ID>"` ผ่าน `db.insert_charges_if_new` เดิม — ไฟล์ช่วงทับกันไม่นับซ้ำ
4. Expense.incurred_on = วันที่ของธุรกรรม (Transaction time) ใน timezone ของไฟล์ (UTC+07:00)
5. แพลตฟอร์มที่ yaml ไม่มี `reports.ads` → upload ล้มเหลวพร้อมข้อความ ไม่ใช่ KeyError

## Consequences
- (+) ค่าแอดที่จ่ายด้วยบัตรเข้า P&L ของ TikTok โดยไม่ต้องพิมพ์เอง และไม่ชนกับ GMV Pay
- (−) ถ้า TikTok เปลี่ยนคำใน Description หรือเพิ่มวิธีจ่ายใหม่ แถวนั้นจะขึ้นเป็นปัญหาจนกว่าจะเพิ่มลง yaml
- (−) คอลัมน์ Account name ไม่ถูก map/เก็บ (อยู่แค่ในไฟล์ดิบ)
- ไม่มีการเปลี่ยน schema; ใช้ตาราง expenses + source_ref เดิม

## Amendment 2026-09-29: Shopee Ads wallet statement
Shopee Ads is a prepaid wallet. Its export (`<username>_adwords_bill_<date>.csv`, metadata lines then a header
`อันดับ,เวลา,รายละเอียด,จำนวน,Remark`) mixes three kinds of rows:
- negative rows — ad credit being used day by day (GMV Max, auto ads, shop ads, Live Ads …) → **skipped**, not new cash;
- `เติมเครดิตอัตโนมัติ (Escrow)` — top-up deducted from the payout, already in the Shopee income report as
  `ค่าธรรมเนียมเติมเงินโฆษณาจากเงิน Escrow` (Settlement.ads_fee) → **skipped**;
- `เติมเครดิต` — the shop tops up with its own money → **ads Expense** for Shopee on that day.
Same cash-basis rule as TikTok: an ad Expense is money that left the shop outside the payout. Recording daily spend
as well would count the same money twice (once at top-up, once when used).
Any other positive row (e.g. an ads refund) is an ImportProblem, never guessed. Skipped rows are counted on the upload.
The file has no transaction id, so `source_ref = "shopee-ads:<date>:<description>:<satang>:<n>"` where n numbers
identical rows within the file — an overlapping later export produces the same refs and adds nothing twice.
Parser `shopee.parse_ads`, options in `config/platforms/shopee.yaml › reports.ads`.
Consequence: a large top-up lands in the month it was paid even if the credit is used later — cash basis, as ADR-0002.
