# ADR-0002: Revenue on cash basis from platform settlement; shared expenses allocated by net_received share

Status: Accepted · Date: 2026-09-27

## Context
เจ้าของกำหนดชัดว่า "เอาเป็นยอดรับจริงเท่านั้น" และต้องการทั้งกำไรต่อออเดอร์และกำไรต่อช่วงเวลา แยก/รวมแพลตฟอร์มได้
ค่าใช้จ่ายบางอย่าง (เงินเดือน ภาษี) ไม่ผูกกับออเดอร์หรือแพลตฟอร์มใด

## Decision
1. รายได้ของออเดอร์ = `Settlement.net_received` ("ยอดที่ปล่อยแล้ว") จากรายงานรายได้ของแพลตฟอร์ม เท่านั้น
2. ช่วงเวลาของ P&L กรองด้วย `settled_at`; Expense กรองด้วย `incurred_on`
3. **Allocation rule** (ฟังก์ชันเดียว `domain/allocation.py`):
   - Expense ที่ระบุ platform → ลง platform นั้นทั้งก้อน
   - Expense `shared` → แบ่งให้แต่ละ platform ตามสัดส่วน Σ net_received ของ platform ในช่วงเวลา
   - ภายใน platform, Expense ของ platform (รวมส่วนที่ได้รับแบ่งมา) → แบ่งลงแต่ละ Settlement ตามสัดส่วน net_received
   - เศษสตางค์จากการปัด ให้ตกที่รายการที่ใหญ่ที่สุด เพื่อให้ Σ ส่วนแบ่ง = ก้อนเดิมเป๊ะ
   - ถ้า Σ net_received ของช่วง = 0 (ไม่มีเงินเข้า) Expense จะไม่ถูกแบ่งลงออเดอร์ แต่ยังอยู่ใน PeriodPnl
4. `OrderProfit = net_received − COGS − allocated Expense`; `PeriodPnl.net_profit = Σ net_received − Σ COGS − Σ Expense`
   และต้องเป็นจริงว่า `Σ OrderProfit == PeriodPnl.net_profit` เมื่อทุกออเดอร์มี COGS ครบ (test บังคับ)

## Alternatives rejected
- Accrual จากรายงานคำสั่งซื้อ: ไม่ตรงคำสั่งเจ้าของ และ COD ทำให้ตัวเลขเกินจริง
- แบ่ง shared เท่ากันต่อออเดอร์: ออเดอร์ 59 บาทจะขาดทุนทุกใบเพียงเพราะเงินเดือน
- แบ่งตามจำนวนชิ้น: ต้องพึ่ง OrderLine ซึ่งอาจอัพโหลดไม่ครบ

## Consequences
- ตัวเลขกำไรของเดือนจะ "ครบ" ก็ต่อเมื่อรายงานรายได้ของเดือนนั้นครบ — UI ต้องบอกวันที่ข้อมูลล่าสุด
- ออเดอร์ที่ยังไม่ปล่อยเงินแสดงเป็น PendingOrder ไม่เข้ากำไร
