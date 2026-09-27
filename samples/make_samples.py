"""Builds two sample Shopee files in the layout the parser expects (header names from config/platforms/shopee.yaml).
Replace with real anonymised exports once available — see README."""

from pathlib import Path

import openpyxl

HERE = Path(__file__).parent

INCOME_HEADERS = [
    "หมายเลขคำสั่งซื้อ", "วันที่ปล่อยเงิน", "ราคาสินค้าเดิม", "ส่วนลดสินค้าจากผู้ขาย", "ค่าคอมมิชชั่น",
    "ค่าธรรมเนียมการทำธุรกรรม", "ค่าธรรมเนียมบริการ", "ค่าคอมมิชชั่น AMS", "ยอดเงินที่ปล่อยแล้ว",
]
INCOME_ROWS = [
    ["2609151234ABCD", "2026-09-15 10:02", 590, -40, -44.00, -17.60, -34.10, -27.50, 426.80],
    ["2609161234EFGH", "2026-09-16 10:02", 290, 0, -23.20, -9.28, -17.98, 0, 239.54],
    ["2609181234IJKL", "2026-09-18 10:02", 1180, -80, -88.00, -35.20, -68.20, -55.00, 853.60],
]
ORDER_HEADERS = [
    "หมายเลขคำสั่งซื้อ", "สถานะการสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ช่องทางการชำระเงิน", "ชื่อสินค้า",
    "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน", "ชื่อผู้ใช้ (ผู้ซื้อ)",
]
ORDER_ROWS = [
    ["2609151234ABCD", "สำเร็จ", "2026-09-10 21:15", "เก็บเงินปลายทาง", "ครีมปนันชิตา 30g", "PNC-CRM-30", 1, "buyer01"],
    ["2609161234EFGH", "สำเร็จ", "2026-09-11 08:40", "ShopeePay", "เซรั่ม 15ml", "PNC-SRM-15", 1, "buyer02"],
    ["2609181234IJKL", "สำเร็จ", "2026-09-12 19:03", "เก็บเงินปลายทาง", "ครีมปนันชิตา 30g", "PNC-CRM-30", 2, "buyer03"],
    ["2609251234MNOP", "กำลังจัดส่ง", "2026-09-25 12:00", "เก็บเงินปลายทาง", "เซรั่ม 15ml", "PNC-SRM-15", 1, "buyer04"],
]


def write(path: Path, preamble: list[list], headers: list[str], rows: list[list]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in preamble:
        ws.append(r)
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


write(HERE / "shopee_income_sample.xlsx", [["รายงานรายได้", "ร้าน pananchita"], []], INCOME_HEADERS, INCOME_ROWS)
write(HERE / "shopee_orders_sample.xlsx", [], ORDER_HEADERS, ORDER_ROWS)
print("ok")
