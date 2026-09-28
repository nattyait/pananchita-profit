# ADR-0006: BaseProduct + ListingMap — cost is entered per base unit, listings map to it with a multiplier

Status: Accepted · Date: 2026-09-28

## Context
ชื่อสินค้าบนแพลตฟอร์ม (ProductKey) เป็น "รายการขาย" ไม่ใช่สินค้าจริง เช่น "[โปร2แถม2] เอสชัวร์ โปร คอฟฟี่" = กาแฟ 4 กล่อง,
"[1 กล่อง] CALCIUM PLUS" = 1 กล่อง สินค้าเดียวกันมีหลายรายการขายในแต่ละแพลตฟอร์ม และต้นทุนต่อกล่องของแต่ละแพลตฟอร์มอาจไม่เท่ากัน
การใส่ต้นทุนต่อรายการขาย (ADR-0003) ทำให้ต้องใส่ซ้ำและผิดง่าย

## Decision
1. **BaseProduct** (สินค้าฐาน): ชื่อไม่ซ้ำ + หน่วย (เช่น "กาแฟเอสชัวร์โปรคอฟฟี่", หน่วย "กล่อง") หนึ่งสินค้าจริงใช้ร่วมกันทุกแพลตฟอร์ม
   เพราะราคาทุนเท่ากัน (เจ้าของยืนยัน 2026-09-28); สิ่งที่ต่างต่อแพลตฟอร์มคือราคาขายที่ตั้ง ซึ่งเก็บที่ ListingMap.unit_price
2. **ListingMap**: ProductKey (1 รายการขาย) → BaseProduct + `units_per_listing` (จำนวนหน่วยฐานต่อ 1 ชิ้นที่ขาย) + `unit_price` (ราคาขายต่อหน่วย ไว้ดู ไม่ใช้คำนวณ)
3. **SkuCost** ยังคีย์ด้วย string `sku` เดิม: ถ้าเป็น BaseProduct ใช้ชื่อสินค้าฐานเป็นคีย์ ถ้าเป็นรายการขายที่ไม่ได้ map ใช้ ProductKey ตรง ๆ (ADR-0003 ยังใช้ได้)
4. COGS ของบรรทัด: ถ้ามี ListingMap → `quantity × units_per_listing × SkuCost(สินค้าฐาน ณ ordered_at)`; ถ้าไม่มี → `quantity × SkuCost(ProductKey)` เดิม
   กฎอยู่ใน `domain/profit.py::effective_unit_cost` ฟังก์ชันเดียว
5. หน้า ต้นทุนสินค้า: รายการขายที่ยังไม่มีต้นทุนจะ "ผูกกับสินค้าฐาน" (เลือกหรือตั้งชื่อใหม่ + จำนวนหน่วย + ราคาต่อหน่วย) แล้วใส่ต้นทุนที่สินค้าฐานครั้งเดียว
6. `ProfitReport.by_base_product`: สรุปต่อสินค้าฐาน โดย quantity นับเป็นหน่วยฐาน (ชิ้น × units_per_listing); `by_product` (ต่อรายการขาย) คงเดิม
7. ลบสินค้าฐานได้เฉพาะตัวที่ไม่มีอะไรคิดต้นทุนผ่านมัน: ไม่มี ListingMap ชี้มา (รวมรายการที่ออเดอร์ถูกยกเลิกหมด) และไม่มี OrderLine
   ที่ ProductKey ตรงกับชื่อนั้น ลบแล้วลบ SkuCost ที่คีย์ด้วยชื่อนั้นด้วย จึงไม่เปลี่ยน COGS ของออเดอร์ไหน (เพิ่ม 2026-09-28)
   กฎอยู่ใน `domain/base_products.py::deletable_base_products`; use case `orchestration/base_products.py::DeleteUnusedBaseProduct`
8. ร้านเปลี่ยนชื่อรายการขายตามโปร ("[โปร2แถม2] X" → "[โปร3แถม2] X") จึงเกิด ProductKey ใหม่ทุกโปร หน้า "ผูกทีละหลายรายการ" แสดง
   ListingMapSuggestion: BaseProduct จากรายการที่ผูกแล้วซึ่ง `title_core` ตรงกัน (เลือกตัวที่ผูกบ่อยสุด) + จำนวนหน่วยเดาจากข้อความโปร
   (ตัวเลือกก่อน แล้วค่อยชื่อ) **ไม่ผูกเองอัตโนมัติ** เพราะจำนวนหน่วยเปลี่ยนตามโปร ถ้าผูกผิดต้นทุนจะผิดเงียบ ๆ; คนยืนยันแล้วกดบันทึกครั้งเดียว
   กฎอยู่ใน `domain/listing_suggestions.py`; use case `orchestration/listing_maps.py::BulkMapListings` (เพิ่ม 2026-09-28)
9. รวมสินค้าฐาน (source → target): ListingMap ของ source ย้ายไป target (units เท่าเดิม), SkuCost ของ source ย้ายไปถ้า target ยังไม่มีราคา
   ไม่งั้นลบทิ้ง, แล้วลบ source ถ้าราคาทั้งสองต่างกันในวันใดวันหนึ่ง COGS ย้อนหลังจะเปลี่ยน → ต้องกดยืนยันแยก
   ห้ามรวมถ้ามี OrderLine ที่ไม่ได้ map ใช้ชื่อ source เป็น ProductKey ตรง ๆ; แก้ชื่อไปเป็นชื่อที่มีอยู่แล้ว = ไปหน้ารวม
   กฎอยู่ใน `domain/base_products.py` (`merge_refusal`, `merge_changes_cogs`); use case `MergeBaseProducts`, `RenameBaseProduct` (เพิ่ม 2026-09-28)
   ทางเลือกที่ยังไม่ทำ (ข้อ 8): อ่าน "SKU ID" ของ TikTok ซึ่งไม่เปลี่ยนตามชื่อ (ช่วยเฉพาะ TikTok และต้องเปลี่ยนนิยาม ProductKey → ต้องมี ADR ใหม่)

## Consequences
- (+) ใส่ต้นทุนครั้งเดียวต่อสินค้าจริง; รายการขายใหม่แค่ผูกเข้าสินค้าฐาน
- (−) เปลี่ยน map ภายหลังมีผลย้อนหลังทุกออเดอร์ (map ไม่ effective-dated); ต้นทุนยัง effective-dated เหมือนเดิม
- ตารางใหม่ 2 ตาราง `base_products`, `listing_maps` (เพิ่มเท่านั้น)
