# ADR-0001: Initial architecture — Functional Core / Imperative Shell, single FastAPI + SQLite app

Status: Accepted · Date: 2026-09-27

## Context
ทีมเล็ก (เจ้าของ + พนักงานไม่กี่คน) ต้องการเว็บที่พนักงานอัพโหลดรายงานแล้วเห็นกำไร ปริมาณข้อมูลเล็ก
(หลักร้อย-พันออเดอร์/เดือน) ต้องเพิ่มแพลตฟอร์มได้โดยไม่พังการคำนวณเดิม และตัวเลขต้องตรวจย้อนกับธนาคารได้

## Decision
- **Modular monolith แบบ 3 ชั้น** ตามชนิดโค้ด: `domain/` (pure), `effects/` (side effects), `orchestration/` (use case)
  และ `web/` เป็น adapter — ไม่แบ่งตามฟีเจอร์
- **Platform = adapter** ใน `domain/platforms/` + yaml mapping; ส่วนที่เหลือรู้จักแค่ `Settlement`, `OrderLine`
- **FastAPI + Jinja2 + SQLite** ไฟล์เดียว รันบนเครื่องเดียว; ไม่มี queue เพราะไฟล์เล็กและ parse เสร็จใน request
- **เงินเป็น integer satang** ทุกที่หลัง parse
- ทิศทาง import: `web → orchestration → effects → domain` (domain ไม่ import ใครเลย)

## Consequences
- (+) profit logic ทดสอบได้โดยไม่ต้องมี DB; เพิ่มแพลตฟอร์มโดยไม่แตะ profit
- (+) รันได้บนโน้ตบุ๊กพนักงาน ไม่ต้องมี infra
- (−) SQLite = ผู้เขียนพร้อมกันได้น้อย ยอมรับได้เพราะอัพโหลดไม่ถี่
- (−) ไม่มี login; ถ้าย้ายออกนอก LAN ต้องมี ADR ใหม่
