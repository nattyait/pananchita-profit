# ADR-0005: TikTok adapter; platform charges not tied to an order become Expense rows on import

Status: Accepted · Date: 2026-09-28

## Context
รายงานรายได้ของ TikTok (income_….xlsx ชีต "รายละเอียดคำสั่งซื้อ") ไม่ได้มีแต่ออเดอร์ มันคือ statement ของบัญชี:
- แถว "คำสั่งซื้อ" — เงินที่ชำระให้ต่อออเดอร์ (ออเดอร์เดียวอาจมีหลายแถวคนละวัน เช่น จ่าย → คืนเงินเมื่อลูกค้าคืนของ)
- แถว "การชำระเงินด้วย GMV สำหรับโฆษณา TikTok" — ค่าโฆษณาที่หักจากยอดโอน (−47,478 ในเดือน ก.ย.) ไม่ผูกออเดอร์
- แถว "ข้อผิดพลาดจากทางร้านค้า" — ค่าปรับ
- แถวจ่าย/หักคืน "การชำระเงินล่วงหน้า" — จังหวะเงินสด หักล้างกันเอง
ไฟล์คำสั่งซื้อเป็น CSV หัวอังกฤษ ไม่มี Seller SKU เกือบทั้งหมด และมีคอลัมน์จำนวนที่คืน

## Decision
1. `Settlement` ของ TikTok = แถวประเภทที่อยู่ใน `options.order_types` เท่านั้น; key `(tiktok, order_id, settled_at)` เดิม
   ทำให้ออเดอร์ที่คืนเงินภายหลังเป็นคนละ Settlement (ยอดติดลบ) และกำไรของช่วงสะท้อนเงินที่ไหลออกจริง
2. แถวใน `options.charge_types` กลายเป็น **Expense** (kind ตาม yaml, platform=tiktok, incurred_on=วันที่แถว, `source_ref`="tiktok:<id>")
   ตอน import; `source_ref` กันซ้ำเมื่ออัพโหลดไฟล์ที่ช่วงเวลาทับกัน ผู้ใช้ไม่ต้องกรอกค่าแอด TikTok เอง
3. แถวใน `options.ignore_types` ไม่นำเข้า
4. fee breakdown: affiliate_fee = ผลรวม 4 คอลัมน์แอฟฟิลิเอต; service_fee = ค่าธรรมเนียมทั้งหมด − (commission + transaction + affiliate + platform);
   other_adjustment = net_received − (product_price + fee_total + shipping + ads) เพื่อให้ product_price + Σfees == net_received เสมอ
5. คำสั่งซื้อ: ProductKey ตาม ADR-0003 โดย variation ที่เป็นค่าเริ่มต้น (`options.default_variations`) ถือว่าไม่มี;
   `quantity` = จำนวน − จำนวนที่คืน (ของคืนมาไม่กิน COGS); `line_amount` อ่านตรงจาก "SKU Subtotal After Discount"
6. โค้ด parse คำสั่งซื้อที่เหมือนกันทุกแพลตฟอร์มย้ายไป `domain/platforms/_common.py`; แต่ละ adapter ส่งแค่ options

## Consequences
- (+) ค่าแอด TikTok เข้าระบบอัตโนมัติจากไฟล์รายได้ ตรงกับเงินที่หายไปจริง
- (−) Expense ที่มาจาก import ลบได้ในหน้า ค่าใช้จ่าย เหมือนรายการที่กรอกเอง — ถ้าลบแล้วอัพโหลดไฟล์เดิมซ้ำจะไม่กลับมา (sha ซ้ำ) ต้อง export ใหม่
- ค่าธรรมเนียมย่อยของ TikTok ยังไม่แสดงแยกทุกตัว (SFP, คูปอง ฯลฯ รวมอยู่ใน service_fee)
