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


def test_bulk_mapping_suggests_base_product_for_renamed_promo_listing(client):
    head = ["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน"]
    old = _xlsx([head, ["A1", "2026-08-10", "[โปร2แถม2] ครีมหน้าใส", "", 1]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("o1.xlsx", old)})
    client.post("/listing-maps", data={"sku": "[โปร2แถม2] ครีมหน้าใส", "base_product": "ครีมหน้าใส", "unit_label": "กล่อง", "units_per_listing": "4"})
    new = _xlsx([head, ["A2", "2026-09-10", "[โปร3แถม2] ครีมหน้าใส", "", 1], ["A3", "2026-09-11", "ชาไทย", "", 1]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("o2.xlsx", new)})
    assert 'href="/listing-maps/bulk"' in client.get("/sku-costs").text
    page = client.get("/listing-maps/bulk").text
    assert 'value="ครีมหน้าใส" placeholder' in page and 'value="5"' in page and "ชาไทย" in page
    r = client.post("/listing-maps/bulk", data={"sku": ["[โปร3แถม2] ครีมหน้าใส", "ชาไทย"], "base_product": ["ครีมหน้าใส", ""],
                                                 "units_per_listing": ["5", ""]})
    assert r.status_code == 200 and "บันทึกแล้ว 1 รายการ" in r.text
    assert "[โปร3แถม2] ครีมหน้าใส" not in r.text and "ชาไทย" in r.text  # saved row leaves the list, blank row stays
    costs = client.get("/sku-costs").text
    assert "× 5 กล่อง" in costs


def test_merge_base_products_and_rename_into_existing_name(client):
    head = ["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน"]
    ords = _xlsx([head, ["A1", "2026-08-10", "[โปร2แถม2] กาแฟ", "", 1], ["A2", "2026-08-10", "[3ถุง] น้ำยา", "", 1],
                  ["A3", "2026-08-10", "[1ลัง] น้ำยา", "", 1]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("o.xlsx", ords)})
    for sku, base, units in (("[โปร2แถม2] กาแฟ", "[โปร2แถม2] กาแฟ", 4), ("[3ถุง] น้ำยา", "[3ถุง] น้ำยา", 3), ("[1ลัง] น้ำยา", "น้ำยา", 6)):
        client.post("/listing-maps", data={"sku": sku, "base_product": base, "unit_label": "ถุง", "units_per_listing": str(units)})
    client.post("/sku-costs", data={"sku": "[3ถุง] น้ำยา", "unit_cost": "97", "effective_from": "2026-05-01"})
    client.post("/sku-costs", data={"sku": "น้ำยา", "unit_cost": "96", "effective_from": "2026-05-01"})
    assert 'href="/base-products/merge?source=' in client.get("/sku-costs").text
    # rename to a name nobody uses: plain rename
    client.post("/base-products/rename", data={"old": "[โปร2แถม2] กาแฟ", "new": "กาแฟ", "unit_label": "กล่อง"})
    assert "× 4 กล่อง" in client.get("/sku-costs").text
    # rename onto an existing base product → goes to the merge page, which warns because 97 ≠ 96
    r = client.post("/base-products/rename", data={"old": "[3ถุง] น้ำยา", "new": "น้ำยา", "unit_label": "ถุง"})
    assert "รวมสินค้าฐาน" in r.text and "ราคาทุนไม่เท่ากัน" in r.text and "97.00" in r.text and "96.00" in r.text
    r = client.post("/base-products/merge", data={"source": "[3ถุง] น้ำยา", "target": "น้ำยา"})  # not confirmed → nothing happens
    assert "ราคาทุนไม่เท่ากัน" in r.text
    client.post("/base-products/merge", data={"source": "[3ถุง] น้ำยา", "target": "น้ำยา", "confirmed": "1"})
    costs = client.get("/sku-costs").text
    assert "[3ถุง] น้ำยา<div" not in costs and "= ต้นทุน 288.00 / ชิ้น" in costs and "= ต้นทุน 576.00 / ชิ้น" in costs
    # renaming onto a name that only has orphan cost rows gives a message, not a server error
    client.post("/sku-costs", data={"sku": "ชื่อที่มีแต่ราคา", "unit_cost": "1", "effective_from": "2026-05-01"})
    r = client.post("/base-products/rename", data={"old": "กาแฟ", "new": "ชื่อที่มีแต่ราคา", "unit_label": ""})
    assert r.status_code == 200 and "ใช้ชื่อ" in r.text and "ไม่ได้" in r.text
    # a name that an unmapped order uses as its own ProductKey cannot be merged away
    client.post("/listing-maps/delete", data={"sku": "[1ลัง] น้ำยา"})
    client.post("/listing-maps", data={"sku": "[โปร2แถม2] กาแฟ", "base_product": "[1ลัง] น้ำยา", "units_per_listing": "1"})
    client.post("/listing-maps", data={"sku": "[โปร2แถม2] กาแฟ", "base_product": "กาแฟ", "units_per_listing": "4"})
    r = client.post("/base-products/merge", data={"source": "[1ลัง] น้ำยา", "target": "กาแฟ", "confirmed": "1"})
    assert "เป็นรหัสสินค้าโดยตรง" in r.text


def test_fully_returned_order_shows_a_label_instead_of_zeros(client):
    inc = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่โอนชำระเงินสำเร็จ", "จำนวนเงินทั้งหมดที่โอนแล้ว (฿)"], ["R1", "2026-08-31", 0]])
    client.post("/upload", data={"platform": "shopee", "kind": "income", "uploaded_by": "เก๋"}, files={"file": ("i.xlsx", inc)})
    ords = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน"], ["R1", "2026-08-30", "โลชั่น", "", 0]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("o.xlsx", ords)})
    page = client.get("/", params={"start": "2026-08-01", "end": "2026-08-31"}).text
    orders = page[page.find("กำไรรายออเดอร์"):]
    assert "คืนสินค้าทั้งหมด" in orders and "ไม่ได้เงินและไม่มีต้นทุน" in orders
    assert "0.00" not in orders.split("รอรับเงิน")[0]


def test_tiktok_ads_statement_adds_card_bills_once(client):
    head = ["Transaction time", "Time zone", "Transaction type", "Transaction subtype", "Account Type", "Account name", "Account ID",
            "Transaction ID", "Description", "Document", "Operator", "Status", "Fund type", "Amount", "Currency"]
    def row(when, subtype, tx, desc, fund, amount):
        return [when, "UTC+07:00", "General", subtype, "ADV", "ร้าน", "1", tx, desc, "D", "-", "Success", fund, amount, "THB"]
    card = "Payment method:\nCredit or debit card"
    rows = [row("2026/09/23 18:44", "Bill payment", "T-GMV", "Payment method:\nGMV Pay", "Credit", "+16107.00"),
            row("2026/09/08 22:38", "Bill payment", "T-CARD", card, "Credit", "+13584.52"),
            row("2026/09/08 22:37", "Issued", "T-FREE", "-", "Ad credit", "+1600.00")]
    r = client.post("/upload", data={"platform": "tiktok", "kind": "ads", "uploaded_by": "เก๋"}, files={"file": ("Transaction_1.xlsx", _xlsx([head, *rows]))})
    assert r.status_code == 200 and "นำเข้าค่าแอด 1 รายการ" in r.text and "GMV Pay" in r.text and "Ad credit" in r.text
    # an overlapping later export with the same card bill must not add it twice
    later = _xlsx([head, rows[1], row("2026/09/16 12:41", "Bill payment", "T-CARD2", card, "Credit", "+181.83")])
    r = client.post("/upload", data={"platform": "tiktok", "kind": "ads", "uploaded_by": "เก๋"}, files={"file": ("Transaction_2.xlsx", later)})
    assert "นำเข้าค่าแอด 1 รายการ (ข้าม 1 รายการที่เคยนำเข้าแล้ว)" in r.text
    expenses = client.get("/expenses").text
    assert expenses.count("13,584.52") == 1 and "181.83" in expenses and "16,107.00" not in expenses and "1,600.00" not in expenses
    r = client.post("/upload", data={"platform": "shopee", "kind": "ads", "uploaded_by": "เก๋"}, files={"file": ("x.xlsx", _xlsx([head]))})
    assert "ยังไม่รองรับรายงานชนิด" in r.text


def test_base_product_detail_finds_and_fixes_a_units_typo(client):
    inc = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่โอนชำระเงินสำเร็จ", "จำนวนเงินทั้งหมดที่โอนแล้ว (฿)"], ["C1", "2026-09-10", 300], ["C2", "2026-09-11", 900]])
    client.post("/upload", data={"platform": "shopee", "kind": "income", "uploaded_by": "เก๋"}, files={"file": ("i.xlsx", inc)})
    head = ["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน"]
    ords = _xlsx([head, ["C1", "2026-09-09", "แคลเซียม สตอเบอรี่", "", 1], ["C2", "2026-09-09", "แคลเซียม 2แถม2", "", 1]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("o.xlsx", ords)})
    client.post("/listing-maps", data={"sku": "แคลเซียม สตอเบอรี่", "base_product": "CALCIUM PLUS", "unit_label": "กล่อง", "units_per_listing": "195"})
    client.post("/listing-maps", data={"sku": "แคลเซียม 2แถม2", "base_product": "CALCIUM PLUS", "units_per_listing": "4"})
    client.post("/sku-costs", data={"sku": "CALCIUM PLUS", "unit_cost": "195", "effective_from": "2026-05-01"})
    assert "1 รายการขายตั้งจำนวนหน่วยสูงผิดปกติ" in client.get("/sku-costs").text
    period = {"start": "2026-09-01", "end": "2026-09-30"}
    assert 'href="/base-products/detail?name=CALCIUM%20PLUS&start=2026-09-01' in client.get("/", params=period).text
    detail = client.get("/base-products/detail", params={"name": "CALCIUM PLUS", **period}).text
    assert "จำนวนหน่วยสูงผิดปกติ" in detail and "-37,725.00" in detail  # 300 − 1 × 195 × 195
    back = "/base-products/detail?name=CALCIUM%20PLUS&start=2026-09-01&end=2026-09-30&platform=all"
    r = client.post("/listing-maps/units", data={"sku": "แคลเซียม สตอเบอรี่", "base_product": "CALCIUM PLUS", "units_per_listing": "1", "back": back})
    assert r.url.path == "/base-products/detail" and "จำนวนหน่วยสูงผิดปกติ" not in r.text and "105.00" in r.text  # 300 − 195
    r = client.post("/listing-maps/units", data={"sku": "แคลเซียม 2แถม2", "base_product": "CALCIUM PLUS", "units_per_listing": "4", "back": "//evil.example"},
                    follow_redirects=False)
    assert r.headers["location"] == "/sku-costs"


def test_upload_then_dashboard_shows_profit(client):
    inc = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่โอนชำระเงินสำเร็จ", "จำนวนเงินทั้งหมดที่โอนแล้ว (฿)"], ["A1", "2026-09-15", 285]])
    r = client.post("/upload", data={"platform": "shopee", "kind": "income", "uploaded_by": "เก๋"}, files={"file": ("inc.xlsx", inc)}, follow_redirects=False)
    assert r.status_code == 303
    before = client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
    assert "ไฟล์ที่ต้อง export" in before and "รายงานคำสั่งซื้อ (ทั้งหมด)" in before and "16/08/2026 – 15/09/2026" in before
    assert 'ยังไม่มีรายการสินค้า (อัพโหลดรายงานคำสั่งซื้อ)\n     · <a href="/upload">' in before
    ords =_xlsx([["หมายเลขคำสั่งซื้อ", "วันที่ทำการสั่งซื้อ", "ชื่อสินค้า", "เลขอ้างอิง SKU (SKU Reference No.)", "จำนวน"], ["A1", "2026-09-10", "ครีม", "PNC-001", 2]])
    client.post("/upload", data={"platform": "shopee", "kind": "orders", "uploaded_by": "เก๋"}, files={"file": ("ord.xlsx", ords)})
    costs = client.get("/sku-costs").text
    assert "ยังไม่มีต้นทุน" in costs and "ผูกสินค้าฐาน" in costs and "ใส่ต้นทุนตรง" not in costs
    unknown = client.get("/", params={"start": "2026-09-01", "end": "2026-09-30"}).text
    assert 'href="/sku-costs?map=PNC-001#map-form"' in unknown  # missing cost links straight to the listing's map form
    problems_box = unknown[unknown.find("รายการที่คิดต้นทุนไม่ได้"):unknown.find("</ul>", unknown.find("รายการที่คิดต้นทุนไม่ได้"))]
    assert "ไม่มีต้นทุนของรายการ PNC-001" in problems_box and 'href="/sku-costs?map=PNC-001#map-form">ผูกสินค้าฐาน / ใส่ต้นทุน' in problems_box
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


def test_upload_time_is_stored_utc_and_shown_in_thai_time(client, monkeypatch):
    from datetime import datetime

    from app.effects import clock
    monkeypatch.setattr(clock, "now_utc", lambda: datetime(2026, 9, 28, 18, 9))
    inc = _xlsx([["หมายเลขคำสั่งซื้อ", "วันที่โอนชำระเงินสำเร็จ", "จำนวนเงินทั้งหมดที่โอนแล้ว (฿)"], ["Z1", "2026-09-15", 100]])
    client.post("/upload", data={"platform": "shopee", "kind": "income", "uploaded_by": "เก๋"}, files={"file": ("z.xlsx", inc)})
    page = client.get("/uploads").text
    assert "29/09/26 01:09" in page and "28/09/26 18:09" not in page
