# CONTEXT.md — Ubiquitous Language ของ Pananchita Profit

> คำศัพท์ทั้งระบบอยู่ที่นี่ที่เดียว ห้ามมีคำพ้อง — ใช้ชื่อในคอลัมน์ "คำ" เป็นชื่อ class / field / ตาราง

## Glossary
| คำ | ความหมาย | หมายเหตุ |
|---|---|---|
| **Platform** | ช่องทางที่ลงออเดอร์: `shopee`, `tiktok`, `facebook` | enum คงที่ ห้าม string อื่น |
| **ReportUpload** | ไฟล์รายงาน 1 ไฟล์ที่พนักงานอัพโหลด พร้อม sha256, ชนิดรายงาน, ผู้อัพ, เวลาอัพ | append-only; ไฟล์ดิบเก็บก่อน parse เสมอ |
| **ReportKind** | ชนิดรายงานจาก platform: `orders` (รายการสั่งซื้อ/สินค้า) หรือ `income` (รายงานรายได้/เงินที่ปล่อย) | Shopee: "รายการคำสั่งซื้อ" และ "รายงานรายได้" |
| **OrderLine** | 1 บรรทัดสินค้าในออเดอร์: order_id, sku (=ProductKey), quantity, ordered_at, status, cancelled, payment_method | มาจาก ReportKind=orders; ใช้คิด COGS และ PendingOrder เท่านั้น |
| **line_amount** | ราคาขายสุทธิต่อชิ้น × จำนวน ของ OrderLine ใช้เป็นน้ำหนักแบ่งเงินของออเดอร์ลงแต่ละบรรทัด | ADR-0004; ไม่ใช่รายได้ |
| **OrderLineProfit** | ส่วนของ OrderProfit ที่ตกกับ 1 บรรทัดสินค้า: share ของ net_received − COGS − share ของ Expense | Σ ทุกบรรทัด = OrderProfit |
| **ProductPnl** | สรุปต่อ ProductKey ในช่วงเวลา: ชิ้น, net_received, COGS, Expense, กำไร | มาจาก OrderLineProfit เท่านั้น |
| **BaseProduct** | สินค้าจริงที่ใส่ต้นทุน: ชื่อไม่ซ้ำ + หน่วย (กล่อง/ถุง) ตั้งแยกต่อแพลตฟอร์มได้ | ADR-0006; ต้นทุนเก็บใน SkuCost โดยใช้ชื่อเป็นคีย์ |
| **ListingMap** | ProductKey → BaseProduct, units_per_listing (หน่วยฐานต่อ 1 ชิ้นที่ขาย), unit_price (ไว้ดู) | ADR-0006 |
| **ListingMapSuggestion** | ข้อเสนอ ListingMap ที่ระบบเดาให้รายการขายที่ยังไม่ผูก: BaseProduct จากรายการที่ผูกแล้วซึ่งชื่อหลัก (ตัดป้ายโปรหน้าชื่อ) ตรงกัน + จำนวนหน่วยจากข้อความโปร | ADR-0006; ไม่บันทึกเอง ต้องมีคนยืนยันทุกแถว |
| **ProductKey** | ตัวตนของสินค้าที่ใช้ผูก SkuCost = SKU ถ้ามี, ถ้าว่าง = `"ชื่อสินค้า | ชื่อตัวเลือก"` | ADR-0003; เก็บในฟิลด์ `sku` |
| **cancelled** | parser ของ platform แปลงสถานะออเดอร์เป็น true/false; domain ไม่รู้จักคำว่า "ยกเลิกแล้ว" | สถานะที่ถือว่ายกเลิกอยู่ใน ColumnMapping |
| **Settlement** | เงินที่ platform **ปล่อยจริง** ให้ 1 ออเดอร์ 1 ครั้ง: net_received (สุทธิหลังหักทุกอย่าง), settled_at, และรายละเอียดค่าธรรมเนียม | **แหล่งรายได้แหล่งเดียวของระบบ** |
| **net_received** | ยอดรับจริง = เงินที่เข้ากระเป๋าผู้ขายหลังหัก commission, service/transaction fee, affiliate | ตัวเลข "ยอดที่ปล่อยแล้ว" ในรายงาน ไม่ใช่คำนวณเอง |
| **settled_at** | วันที่ platform ปล่อยเงิน | ใช้เลือกช่วงเวลาของ P&L เสมอ |
| **ordered_at** | วันที่ลูกค้าสั่ง | ใช้เลือก SkuCost ที่มีผล ณ วันนั้น ไม่ใช้เลือกช่วง P&L |
| **fee breakdown** | commission_fee, service_fee, transaction_fee, affiliate_fee, tax_fee, platform_fee, ads_fee, shipping_fee_diff, other_adjustment | เก็บไว้เพื่ออธิบาย ไม่ใช่เพื่อคำนวณ net_received |
| **SkuCost** | ต้นทุนต่อชิ้นของ SKU มีผลตั้งแต่ effective_from | effective-dated; ไม่แก้ย้อนหลัง เพิ่มแถวใหม่แทน |
| **COGS** | ต้นทุนสินค้าของออเดอร์ = Σ quantity × (units_per_listing × SkuCost ของ BaseProduct ถ้า map ไว้ ไม่งั้น SkuCost ของ ProductKey) ณ ordered_at | ถ้า SKU ไม่มีต้นทุน → เป็น "ปัญหา" ไม่ใช่ 0 |
| **Expense** | ค่าใช้จ่ายตามช่วงเวลา: kind (`ads`, `staff`, `tax`, `other`), amount, incurred_on, platform (หรือ `shared`), source_ref | เข้าคิด P&L ตาม incurred_on |
| **PlatformCharge** | Expense ที่แพลตฟอร์มหักจากยอดโอนโดยไม่ผูกออเดอร์ (เช่น ค่าแอด GMV Max ของ TikTok) นำเข้าจากรายงานรายได้; `source_ref` = `<platform>:<transaction id>` กันซ้ำ | ADR-0005 |
| **shared** | ค่าใช้จ่ายที่ไม่ผูกกับ platform เดียว เช่น เงินเดือน ภาษี | ถูก **allocate** ตามสัดส่วน net_received |
| **Allocation** | กฎกระจาย Expense ลงสู่ platform และ order ตามสัดส่วน net_received ในช่วงเวลา | ADR-0002; ฟังก์ชันเดียวใน `domain/allocation.py` |
| **OrderContribution** | กำไรขั้นต้นต่อออเดอร์ = net_received − COGS | ไม่รวมค่าใช้จ่ายส่วนกลาง |
| **OrderProfit** | กำไรสุทธิต่อออเดอร์ = OrderContribution − allocated Expense | ตัวเลขที่ตอบว่า "ออเดอร์นี้กำไรจริงไหม" |
| **PeriodPnl** | สรุปช่วงเวลา (ต่อ platform หรือรวม): Σ net_received, Σ COGS, Expense แต่ละ kind, กำไรสุทธิ | ตัวเลขบนหน้า Dashboard |
| **PendingOrder** | ออเดอร์ที่มี OrderLine ที่ไม่ถูกยกเลิก แต่ยังไม่มี Settlement (เช่น COD ยังไม่ปล่อยเงิน) | แสดงเป็น "รอรับเงิน" เสมอ |
| **MissingReport** | ไฟล์ที่พนักงานควร export เพิ่ม: Platform + ReportKind + ช่วงวันที่ (กรองตาม `ordered_at` หรือ `settled_at`) + จำนวนออเดอร์ | Settlement ไม่มี OrderLine → `orders` ตาม ordered_at; PendingOrder → `income` ตาม settled_at; คำนวณใน `domain/missing_reports.py` |
| **ImportProblem** | สิ่งที่ parser แปลงไม่ได้/หาคอลัมน์ไม่เจอ/SKU ไม่มีต้นทุน | ต้องแสดงให้ผู้ใช้เห็น ห้ามข้าม |
| **ColumnMapping** | ไฟล์ `config/platforms/<platform>.yaml` บอกว่า field ไหนอ่านจากหัวคอลัมน์ชื่ออะไรได้บ้าง | ข้อมูล ไม่ใช่โค้ด |

## คำต้องห้าม (ห้ามใช้เป็นชื่อ concept)
- `revenue`, `sales`, `income` เป็นชื่อ field (ใช้ `net_received` แทน) — คำเหล่านี้ทำให้คนเข้าใจว่าเป็นราคาขาย
- `payout`, `release`, `disbursement` (ใช้ `Settlement` / `settled_at` แทน)
- `cost` ลอย ๆ (ต้องระบุว่า `SkuCost`, `COGS` หรือ `Expense`)
- `date` ลอย ๆ (ต้องเป็น `ordered_at`, `settled_at`, `incurred_on`, `uploaded_at`)
- `profit` ลอย ๆ (ต้องเป็น `OrderContribution`, `OrderProfit` หรือ `PeriodPnl.net_profit`)
- `overhead` (ใช้ `shared` Expense แทน)
