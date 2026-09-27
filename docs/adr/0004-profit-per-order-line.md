# ADR-0004: Order money is split across its lines by line_amount; profit is reported per ProductKey

Status: Accepted · Date: 2026-09-28

## Context
เจ้าของต้องการเห็นกำไรรายออเดอร์**แยกตามสินค้า** และกำไรรวมต่อสินค้าในช่วงเวลา แต่ Settlement มาเป็นก้อนต่อออเดอร์
ออเดอร์ที่มีหลายสินค้าจึงต้องมีกฎแบ่งเงิน (ADR-0003 ระบุว่าจะตัดสินใจเมื่อมีเคส)

## Decision
1. `OrderLine` เพิ่ม `line_amount` = ราคาขายสุทธิต่อชิ้น × จำนวน (จากรายงานคำสั่งซื้อ; 0 ถ้าไม่มีคอลัมน์)
2. `net_received`, `allocated_expense` และ fee ของออเดอร์ถูกแบ่งลงแต่ละบรรทัดด้วย `split_proportionally` ตาม `line_amount`
   ถ้าทุกบรรทัดเป็น 0 ให้แบ่งตาม `quantity` — เศษสตางค์ตกที่บรรทัดใหญ่สุด (กฎเดิมของ ADR-0002)
3. COGS ของบรรทัด = quantity × SkuCost ณ ordered_at (ไม่ต้องแบ่ง)
4. `OrderLineProfit` = share ของ net_received − COGS − share ของ allocated_expense; Σ ของทุกบรรทัด == OrderProfit เสมอ (test บังคับ)
5. `ProfitReport.by_product` สรุปต่อ ProductKey: จำนวนชิ้น, Σ net_received, Σ COGS, Σ expense, กำไร — นับเฉพาะออเดอร์ที่ได้เงินในช่วง

## Alternatives rejected
- แบ่งตามต้นทุน: สินค้ากำไรสูงจะถูกกดกำไรลง
- ไม่แบ่ง แสดงเฉพาะออเดอร์เดี่ยว: ออเดอร์หลายสินค้าจะหายจากรายงานสินค้า

## Consequences
- ออเดอร์ที่ยังไม่มีรายการสินค้า (ไม่ได้อัพโหลดรายงานคำสั่งซื้อ) ไม่ปรากฏในสรุปต่อสินค้า และยังขึ้นเป็นปัญหาเหมือนเดิม
