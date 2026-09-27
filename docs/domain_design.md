# Domain Design — Pananchita Profit

## ปัญหาที่แก้
เจ้าของแบรนด์ปนันชิตาขายผ่าน Shopee, TikTok, Facebook และไม่รู้ว่า "ออเดอร์นี้กำไรจริงไหม" เพราะ
- ราคาขายบนแพลตฟอร์ม ≠ เงินที่ได้รับ (หัก commission, service fee, transaction fee, affiliate)
- COD ทำให้เงินเข้าช้าและบางออเดอร์ตีกลับ
- ต้นทุนสินค้า ค่าแอด เงินเดือน ภาษี กระจายอยู่คนละที่

## หลักการตั้งต้น (ทำไมถึงออกแบบแบบนี้)
1. **Cash basis จากรายงานรายได้ของแพลตฟอร์ม** — รายได้ = "ยอดที่ปล่อยแล้ว" ที่แพลตฟอร์มรายงาน ไม่คำนวณเองจากราคาสินค้า−ค่าธรรมเนียม
   เพราะแพลตฟอร์มเป็นคนหักจริงและตัวเลขมันจะตรงกับเงินเข้าธนาคาร
2. **สองรายงานต่อแพลตฟอร์ม** — รายงานรายได้ไม่มี SKU/จำนวน ส่วนรายงานคำสั่งซื้อไม่มียอดปล่อยเงิน จึงต้องใช้ทั้งคู่ ชนกันด้วย `order_id`
3. **ช่วงเวลาตามวันปล่อยเงิน** — ตอบคำถาม "เดือนนี้เงินเข้ามาเท่าไรและกำไรเท่าไร" ไม่ใช่ "เดือนนี้ขายได้เท่าไร"
4. **ค่าใช้จ่ายส่วนกลางกระจายตามสัดส่วน net_received** — ทางเลือกอื่น (กระจายเท่ากันต่อออเดอร์) ลงโทษออเดอร์เล็ก ส่วนกระจายตามจำนวนชิ้นไม่สะท้อนแพลตฟอร์มที่ทำเงิน ดู ADR-0002
5. **ไฟล์ดิบเก็บก่อนเสมอ** — parser ของแพลตฟอร์มพังได้ทุกครั้งที่แพลตฟอร์มเปลี่ยนหัวคอลัมน์ ต้อง re-run ได้

## Bounded contexts (โฟลเดอร์ใน app/)
| Context | หน้าที่ | Kind |
|---|---|---|
| `domain/platforms/<p>.py` | แปลงแถวจากรายงาน → `Settlement` / `OrderLine` ตาม ColumnMapping | pure |
| `domain/mapping.py` | จับหัวคอลัมน์ในไฟล์กับ field ใน yaml | pure |
| `domain/profit.py` | COGS, OrderContribution, PeriodPnl | pure |
| `domain/allocation.py` | กระจาย Expense (ADR-0002) | pure |
| `effects/db.py` | ตาราง + ฟังก์ชันอ่าน/เขียนแบบโง่ ๆ | effect |
| `effects/file_store.py` | เก็บ/อ่านไฟล์ดิบ + sha256 | effect |
| `effects/report_reader.py` | xlsx/csv → list[dict] | effect |
| `orchestration/import_report.py` | อัพโหลด: เก็บไฟล์ → อ่าน → map → parse → บันทึก → รายงานปัญหา | orchestration |
| `orchestration/profit_report.py` | ช่วงเวลา+platform → PeriodPnl + รายการ OrderProfit + PendingOrder | orchestration |
| `web/` | FastAPI routes + Jinja templates ภาษาไทย | adapter |

## Flow หลัก
```
staff อัพโหลดไฟล์ ──► file_store.save (bytes, sha256)        [effect]
                 ──► db.insert ReportUpload(status=received)  [effect]
                 ──► report_reader.rows(bytes)                 [effect]
                 ──► mapping.resolve(headers, yaml)           [pure]
                 ──► platforms.shopee.parse_*(rows, mapping)  [pure]  → values + ImportProblems
                 ──► db.insert Settlement / OrderLine (idempotent keys) [effect]
                 ──► db.update ReportUpload(status, counts, problems)  [effect]  (upload row = status only; content append-only)
```
```
dashboard(from, to, platform?) ──► db.settlements_between(settled_at) + order_lines_for(order_ids)
                                    + sku_costs + expenses_between(incurred_on)            [effect]
                               ──► profit.build_report(...)                                [pure]
                               ──► render                                                   [adapter]
```

## สิ่งที่ตั้งใจ *ไม่* ทำใน v1
- ไม่มี login/สิทธิ์ — ใช้ใน LAN
- ไม่ sync API แพลตฟอร์ม — อัพโหลดไฟล์เท่านั้น (API ต้องขออนุมัติและเปลี่ยนบ่อย)
- ไม่คิด VAT อัตโนมัติ — ภาษีกรอกเป็น Expense kind=`tax`
- ไม่แยกค่าส่งที่ผู้ขายรับผิดชอบเป็น field พิเศษ — อยู่ใน net_received แล้วตามที่แพลตฟอร์มหัก

## การเพิ่มแพลตฟอร์ม (Facebook)
1. `config/platforms/tiktok.yaml` ระบุหัวคอลัมน์
2. `app/domain/platforms/tiktok.py` มีฟังก์ชัน `parse_income(rows, mapping)` และ `parse_orders(rows, mapping)` คืน type เดียวกับ Shopee
3. ลงทะเบียนใน `app/domain/platforms/__init__.py`
4. tests/domain/platforms/test_tiktok.py จากไฟล์จริง (ลบข้อมูลลูกค้าออก)
ห้ามแตะ `profit.py` — ถ้าจำเป็น = ADR ใหม่
