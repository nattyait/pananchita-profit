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


def test_cost_form_saves_when_base_product_typed_without_hidden_name(client):
    # production bug 2026-09-28: typing a base product into the box leaves hidden product_name empty → 422
    r = client.post("/sku-costs", data={"sku": "AM WOW", "product_name": "", "unit_cost": "96", "effective_from": "2026-05-01"})
    assert r.status_code == 200 and "96.00" in r.text
    r = client.post("/sku-costs", data={"sku": "AM WOW", "product_name": "", "unit_cost": "97", "effective_from": "2026-05-01"})
    assert r.status_code == 200 and "97.00" in r.text and "96.00" not in r.text  # same product + date replaces
    r = client.post("/sku-costs/1/edit", data={"sku": "AM WOW", "product_name": "", "unit_cost": "95", "effective_from": "2026-05-01"})
    assert r.status_code == 200 and "95.00" in r.text


def test_upload_then_dashboard_shows_profit(client):
    inc = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่โอนชำระเงินสำเร็จ", "จำนวนเงินทั้งหมดที่โอนแล้ว (฿)"], ["A1", "2026-09-15", 285]])
    r = client.post("/upload", data={"platform": "shopee", "kind": "income", "uploaded_by": "เก๋"}, files={"file": ("inc.xlsx", inc)}, follow_redirects=False)
    assert r.status_code == 303
    ords = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน"], ["A1", "2026-09-10", "ครีม", "PNC-001", 2]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("ord.xlsx", ords)})
    costs = client.get("/sku-costs").text
    assert "ยังไม่มีต้นทุน" in costs and "ผูกสินค้าฐาน" in costs and "ใส่ต้นทุนตรง" not in costs
    unknown = client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
    assert 'href="/sku-costs?map=PNC-001#map-form"' in unknown  # missing cost links straight to the listing's map form
    client.post("/sku-costs", data={"sku": "PNC-001", "product_name": "ครีม", "unit_cost": "50", "effective_from": "2026-01-01"})
    assert "map=PNC-001" not in client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
    client.post("/expenses", data={"kind": "ads", "platform": "shopee", "amount": "35", "incurred_on": "2026-09-20", "note": ""})
    page =client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
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
    import re

    costs_html = client.get("/sku-costs").text
    cost_id = re.search(r"ครีมฐาน</td>\s*<td class=\"n\">20.00</td>.*?/sku-costs/(\d+)/edit", costs_html, re.S).group(1)
    edit_page = client.get(f"/sku-costs/{cost_id}/edit").text
    assert "จำนวนหน่วยของแต่ละรายการขาย" in edit_page and 'value="2"' in edit_page
    client.post("/listing-maps/units", data={"sku": "PNC-001", "base_product": "ครีมฐาน", "units_per_listing": "3", "back": f"/sku-costs/{cost_id}/edit"})
    assert "60.00" in client.get(f"/sku-costs/{cost_id}/edit").text  # 3 boxes × 20
    client.post("/listing-maps/units", data={"sku": "PNC-001", "base_product": "ครีมฐาน", "units_per_listing": "2"})
    client.post("/base-products/rename", data={"old": "ครีมฐาน", "new": "ครีม", "unit_label": "หลอด"})
    costs_page = client.get("/sku-costs").text
    assert "ครีม" in costs_page and "หลอด" in costs_page and "= ต้นทุน 40.00 / ชิ้น" in costs_page
    # an unused base product can be deleted; one with a listing mapped cannot
    client.post("/sku-costs", data={"sku": "กาแฟว่าง", "unit_cost": "110", "effective_from": "2026-05-01"})
    client.post("/listing-maps", data={"sku": "X-NEW", "base_product": "กาแฟว่าง", "unit_label": "กล่อง", "units_per_listing": "1"})
    client.post("/listing-maps/delete", data={"sku": "X-NEW"})
    assert 'name="name" value="กาแฟว่าง"' in client.get("/sku-costs").text
    assert 'name="name" value="ครีม"' not in client.get("/sku-costs").text
    client.post("/base-products/delete", data={"name": "ครีม"})
    assert "= ต้นทุน 40.00 / ชิ้น" in client.get("/sku-costs").text
    client.post("/base-products/delete", data={"name": "กาแฟว่าง"})
    assert "กาแฟว่าง" not in client.get("/sku-costs").text
    assert client.get("/uploads").status_code == 200
    assert "A1" not in client.get("/", params={"start": "2026-10-01", "end": "2026-10-31", "platform": "shopee"}).text.split("รอรับเงิน")[0]
