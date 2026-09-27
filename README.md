# Pananchita Profit — กำไรจริงต่อออเดอร์

เว็บสำหรับทีมปนันชิตา: พนักงานอัพโหลดรายงานจากแพลตฟอร์ม (เริ่มที่ Shopee) → ระบบชนกับต้นทุนสินค้า ค่าแอด
ค่าพนักงาน ภาษี → แสดงกำไรจริงต่อออเดอร์และต่อช่วงเวลา แยกหรือรวมแพลตฟอร์ม โดยนับ **เฉพาะเงินที่แพลตฟอร์มปล่อยแล้ว**

กฎของโปรเจกต์อยู่ใน `CLAUDE.md` (behavioral contract) · คำศัพท์ใน `CONTEXT.md` · เหตุผลใน `docs/`

## เริ่มใช้งาน
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
make install          # pip install -e ".[dev]"
make test             # ต้องผ่านทั้งหมด
make run              # เปิด http://localhost:8000
```
ข้อมูลทั้งหมดอยู่ใน `data/` (`app.db` + `uploads/`) — สำรองโฟลเดอร์นี้ทุกคืน

## Deploy บน Railway (ผ่าน GitHub)
```bash
git remote add origin https://github.com/<user>/pananchita-profit.git
git push -u origin main
```
บน Railway: **New Project › Deploy from GitHub repo** เลือก repo นี้ (มี `Dockerfile` + `railway.json` แล้ว) จากนั้น
1. **Volume** — Add Volume ให้ service, mount path `/data` (ถ้าไม่ทำ ข้อมูลหายทุกครั้งที่ deploy ใหม่)
2. **Variables** — `PNC_DATA_DIR=/data` (Dockerfile ตั้งไว้แล้ว แต่ใส่ซ้ำได้)
3. **Settings › Networking › Generate Domain** — ได้ URL ให้พนักงานเปิดใช้

ยังไม่มี login ใน v1 — ถ้าเปิดสาธารณะ ให้ใส่ Railway private networking หรือเพิ่ม basic auth ก่อน (มี issue ใน ADR ถัดไป)

## ลำดับการใช้ (ครั้งแรก)
1. **ต้นทุนสินค้า** — ใส่ต้นทุน/ชิ้นของทุก SKU พร้อมวันที่มีผล
2. **อัพโหลดรายงาน** Shopee ทั้งสองไฟล์
   - รายงานรายได้ (การเงิน › รายได้ของฉัน › ปล่อยแล้ว › ดาวน์โหลด) → ยอดรับจริง
   - รายงานคำสั่งซื้อ (คำสั่งซื้อ › ส่งออก) → SKU/จำนวน และออเดอร์ที่ยังรอเงิน
3. **ค่าใช้จ่าย** — ค่าแอด (ระบุแพลตฟอร์ม), เงินเดือน/ภาษี (ส่วนกลาง)
4. หน้า **กำไร** เลือกช่วงวันที่ + แพลตฟอร์ม

ทดลองด้วยไฟล์ใน `samples/` ได้เลย (`make samples` สร้างใหม่)

## ถ้าอัพโหลดแล้วขึ้น "ล้มเหลว: หาแถวหัวคอลัมน์ไม่เจอ"
Shopee เปลี่ยนชื่อคอลัมน์ได้ — เปิดไฟล์ดูชื่อหัวคอลัมน์จริง แล้วเพิ่มชื่อนั้นใน `config/platforms/shopee.yaml`
(ไม่ต้องแก้โค้ด) จากนั้นอัพโหลดใหม่ ไฟล์เดิมยังเก็บอยู่ใน `data/uploads/` เสมอ

## โครงสร้าง
```
app/domain/         pure logic: parser Shopee, mapping, profit, allocation   (tests/domain = spec)
app/effects/        DB (SQLite), เก็บไฟล์, อ่าน xlsx/csv
app/orchestration/  use case: ImportReport, BuildProfitReport
app/web/            FastAPI + Jinja (ภาษาไทย)
config/platforms/   ชื่อคอลัมน์ต่อแพลตฟอร์ม (ข้อมูล ไม่ใช่โค้ด)
```
เพิ่ม TikTok/Facebook: ดู `docs/domain_design.md` หัวข้อ "การเพิ่มแพลตฟอร์ม"
