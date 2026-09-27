from datetime import date, datetime
from pathlib import Path

import openpyxl

from app.domain.types import Platform, ReportKind
from app.effects import db
from app.orchestration.import_report import ImportReport
from app.orchestration.profit_report import BuildProfitReport

CONFIG = Path("config/platforms")


def _xlsx(rows, extra_first_sheet=None):
    import io

    wb = openpyxl.Workbook()
    ws = wb.active
    if extra_first_sheet is not None:  # mimic Shopee: summary sheet first, data second
        for r in extra_first_sheet:
            ws.append(r)
        ws = wb.create_sheet("Income")
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_flow_end_to_end(tmp_path):
    s = db.make_session_factory("sqlite:///:memory:")()
    uc = ImportReport(s, tmp_path / "uploads", CONFIG, now=datetime(2026, 9, 27))
    income = _xlsx([
        ["ยอดรวม (฿)"],
        ["หมายเลขคำสั่งซื้อ", "วันที่โอนชำระเงินสำเร็จ", "ค่าคอมมิชชั่น", "ค่าคอมมิชชั่น AMS", "จำนวนเงินทั้งหมดที่โอนแล้ว (฿)", "ชื่อผู้ใช้ (ผู้ซื้อ)"],
        ["A1", "2026-09-15", -10, -5, 285, "ลูกค้า"],
        ["A2", "2026-09-16", -3, 0, "ผิด", "ลูกค้า"],
    ], extra_first_sheet=[["รายงานรายรับของฉัน"], ["จาก", "2026-09-01"]])
    out = uc.run(platform=Platform.SHOPEE, kind=ReportKind.INCOME, filename="income.xlsx", data=income, uploaded_by="เก๋")
    assert out.status == "imported" and out.row_count == 1 and "แถว 4" in out.problems[0]
    assert (tmp_path / "uploads").glob("*.xlsx")

    again = uc.run(platform=Platform.SHOPEE, kind=ReportKind.INCOME, filename="income.xlsx", data=income, uploaded_by="เก๋")
    assert again.status == "duplicate" and again.upload_id == out.upload_id

    orders = _xlsx([
        ["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "สถานะการสั่งซื้อ", "ชื่อสินค้า", "ชื่อตัวเลือก", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน", "ช่องทางการชำระเงิน"],
        ["A1", "2026-09-10 09:00", "สำเร็จแล้ว", "ครีม", "30g", "", 2, "COD"],
        ["COD9", "2026-09-20 09:00", "กำลังจัดส่ง", "ครีม", "30g", "", 1, "COD"],
        ["X1", "2026-09-21 09:00", "ยกเลิกแล้ว", "ครีม", "30g", "", 1, "COD"],
    ])
    assert uc.run(platform=Platform.SHOPEE, kind=ReportKind.ORDERS, filename="orders.xlsx", data=orders, uploaded_by="เก๋").status == "imported"
    db.insert_sku_cost(s, sku="ครีม | 30g", product_name="ครีม", unit_cost=5000, effective_from=date(2026, 1, 1))
    s.commit()

    report = BuildProfitReport(s).run(start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert report.total.net_received == 28500 and report.total.cogs == 10000 and report.total.net_profit == 18500
    assert report.orders[0].fee_total == -1500
    assert [p.order_id for p in report.pending] == ["COD9"]


def test_wrong_file_is_failed_not_swallowed(tmp_path):
    s = db.make_session_factory("sqlite:///:memory:")()
    uc = ImportReport(s, tmp_path, CONFIG)
    out = uc.run(platform=Platform.SHOPEE, kind=ReportKind.INCOME, filename="x.xlsx", data=_xlsx([["a", "b"]]), uploaded_by="เก๋")
    assert out.status == "failed" and "หัวคอลัมน์" in out.error
    assert db.get_upload(s, out.upload_id).status == "failed"
