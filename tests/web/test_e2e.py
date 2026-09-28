"""One happy path per user-facing flow: upload → costs → expenses → see profit."""
import io

import openpyxl
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PNC_DB_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("PNC_UPLOAD_ROOT", str(tmp_path / "uploads"))
    import importlib

    from app.web import main, settings

    importlib.reload(settings)
    importlib.reload(main)
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _xlsx(rows):
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_then_dashboard_shows_profit(client):
    inc = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่โอนชำระเงินสำเร็จ", "จำนวนเงินทั้งหมดที่โอนแล้ว (฿)"], ["A1", "2026-09-15", 285]])
    r = client.post("/upload", data={"platform": "shopee", "kind": "income", "uploaded_by": "เก๋"}, files={"file": ("inc.xlsx", inc)}, follow_redirects=False)
    assert r.status_code == 303
    ords = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน"], ["A1", "2026-09-10", "ครีม", "PNC-001", 2]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("ord.xlsx", ords)})
    costs = client.get("/sku-costs").text
    assert "ยังไม่มีต้นทุน" in costs and "ผูกสินค้าฐาน" in costs and "ใส่ต้นทุนตรง" not in costs
    client.post("/sku-costs", data={"sku": "PNC-001", "product_name": "ครีม", "unit_cost": "50", "effective_from": "2026-01-01"})
    client.post("/expenses", data={"kind": "ads", "platform": "shopee", "amount": "35", "incurred_on": "2026-09-20", "note": ""})
    page = client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
    assert "285.00" in page and "100.00" in page and "150.00" in page  # net, cogs, profit 285-100-35
    assert "กำไรตามรายการขาย" in page and "75.00" in page  # profit per unit: 150 / 2 pieces
    assert "ขาดทุน" not in page
    # edit the cost row: 50 → 60 changes profit 150 → 130; a duplicate (sku, date) is rejected with a message
    client.post("/sku-costs", data={"sku": "PNC-001", "product_name": "ครีม", "unit_cost": "99", "effective_from": "2026-12-01"})  # future row, not effective yet
    edit = client.get("/sku-costs/1/edit")
    assert edit.status_code == 200 and 'value="50.00"' in edit.text
    client.post("/sku-costs/1/edit", data={"sku": "PNC-001", "product_name": "ครีม 30g", "unit_cost": "60", "effective_from": "2026-01-01"})
    assert "130.00" in client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
    dup = client.post("/sku-costs/1/edit", data={"sku": "PNC-001", "product_name": "x", "unit_cost": "1", "effective_from": "2026-12-01"}, follow_redirects=True)
    assert "อยู่แล้ว" in dup.text
    client.post("/sku-costs/2/delete")
    assert "99.00" not in client.get("/sku-costs").text
    # ADR-0006: map the listing to a base product (1 piece = 2 boxes at 20/box → 40 per piece, 2 pieces → 80)
    form = {"sku": "PNC-001", "base_product": "ครีมฐาน", "unit_label": "กล่อง", "units_per_listing": "2", "unit_price": "100"}
    r = client.post("/listing-maps", data=form, follow_redirects=True)
    assert 'value="ครีมฐาน"' in r.text  # redirected to the cost form for the new base product
    client.post("/sku-costs", data={"sku": "ครีมฐาน", "product_name": "ครีมฐาน", "unit_cost": "20", "effective_from": "2026-01-01"})
    page = client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
    assert "กำไรตามสินค้าฐาน" in page and "80.00" in page
    client.post("/base-products/rename", data={"old": "ครีมฐาน", "new": "ครีม", "unit_label": "หลอด"})
    costs_page = client.get("/sku-costs").text
    assert "ครีม" in costs_page and "หลอด" in costs_page and "= ต้นทุน 40.00 / ชิ้น" in costs_page
    assert client.get("/uploads").status_code == 200
    assert "A1" not in client.get("/", params={"start": "2026-10-01", "end": "2026-10-31", "platform": "shopee"}).text.split("รอรับเงิน")[0]
