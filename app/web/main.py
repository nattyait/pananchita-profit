"""HTTP adapter. Routes parse input → call one use case → render. No SQL, no arithmetic, no business `if`."""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.money import baht, parse_money
from app.domain.types import SHARED, ExpenseKind, Platform, ReportKind
from app.effects import db, file_store
from app.orchestration.import_report import ImportReport
from app.orchestration.profit_report import BuildProfitReport
from app.web import settings

app = FastAPI(title="Pananchita Profit")
app.mount("/static", StaticFiles(directory=settings.STATIC), name="static")
templates = Jinja2Templates(directory=settings.TEMPLATES)
templates.env.filters["baht"] = baht
templates.env.globals.update(
    PLATFORMS=[(p.value, name) for p, name in ((Platform.SHOPEE, "Shopee"), (Platform.TIKTOK, "TikTok"), (Platform.FACEBOOK, "Facebook"))],
    KINDS=[(ReportKind.INCOME.value, "รายงานรายรับ (โอนเงินสำเร็จ)"), (ReportKind.ORDERS.value, "รายงานคำสั่งซื้อ (ทั้งหมด)")],
    EXPENSE_KINDS=[(ExpenseKind.ADS.value, "ค่าแอด"), (ExpenseKind.STAFF.value, "ค่าพนักงาน"), (ExpenseKind.TAX.value, "ภาษี"), (ExpenseKind.OTHER.value, "อื่น ๆ")],
    SHARED=SHARED,
)
SessionFactory = db.make_session_factory(settings.DB_URL)


def session() -> Session:
    s = SessionFactory()
    try:
        yield s
    finally:
        s.close()


Db = Annotated[Session, Depends(session)]


def _render(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx)


def _default_period(today: date) -> tuple[date, date]:
    return today.replace(day=1), today


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, s: Db, start: date | None = None, end: date | None = None, platform: str = "all"):
    d_start, d_end = _default_period(date.today())
    start, end = start or d_start, end or d_end
    chosen = Platform(platform) if platform in Platform._value2member_map_ else None
    report = BuildProfitReport(s).run(start=start, end=end, platform=chosen)
    return _render(request, "dashboard.html", report=report, start=start, end=end, platform=platform, ExpenseKind=ExpenseKind)


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, outcome: str | None = None):
    return _render(request, "upload.html", outcome=outcome)


@app.post("/upload")
async def upload(s: Db, platform: Annotated[str, Form()], kind: Annotated[str, Form()], uploaded_by: Annotated[str, Form()], file: UploadFile):
    data = await file.read()
    outcome = ImportReport(s, settings.UPLOAD_ROOT, settings.CONFIG_ROOT, now=datetime.now()).run(
        platform=Platform(platform), kind=ReportKind(kind), filename=file.filename or "report", data=data, uploaded_by=uploaded_by.strip(),
    )
    return RedirectResponse(f"/uploads?highlight={outcome.upload_id}", status_code=303)


@app.get("/uploads", response_class=HTMLResponse)
def uploads(request: Request, s: Db, highlight: int | None = None):
    return _render(request, "uploads.html", uploads=db.list_uploads(s), highlight=highlight)


@app.get("/uploads/{upload_id}/download")
def download(s: Db, upload_id: int):
    row = db.get_upload(s, upload_id)
    if row is None:
        return Response(status_code=404)
    data = file_store.load(settings.UPLOAD_ROOT, row.sha256, row.filename)
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{row.filename}"'})


@app.get("/sku-costs", response_class=HTMLResponse)
def sku_costs(request: Request, s: Db):
    seen = db.products_seen(s)
    base_products = db.list_base_products(s)
    have = {r.sku for r in db.list_sku_cost_rows(s)}
    return _render(request, "sku_costs.html", rows=db.list_sku_cost_rows(s), missing=[p for p in seen if not p.has_cost],
                   seen_by_sku={p.sku: p for p in seen}, today=date.today(), prefill=request.query_params.get("sku", ""),
                   base_products=base_products, base_without_cost=[b for b in base_products if b.name not in have],
                   listings_by_base={b.name: [p for p in seen if p.base_product == b.name] for b in base_products},
                   map_sku=request.query_params.get("map", ""), rename=request.query_params.get("rename", ""),
                   latest_cost={r.sku: r.unit_cost for r in sorted(db.list_sku_cost_rows(s), key=lambda r: r.effective_from)})


@app.post("/listing-maps")
def save_listing_map(s: Db, sku: Annotated[str, Form()], base_product: Annotated[str, Form()], units_per_listing: Annotated[int, Form()],
                     unit_label: Annotated[str, Form()] = "", unit_price: Annotated[str, Form()] = ""):
    name = base_product.strip()
    db.upsert_base_product(s, name=name, unit_label=unit_label.strip())
    db.upsert_listing_map(s, sku=sku.strip(), base_product=name, units_per_listing=max(units_per_listing, 1),
                          unit_price=parse_money(unit_price) if unit_price.strip() else 0)
    s.commit()
    return RedirectResponse(f"/sku-costs?sku={quote(name)}#cost-form" if name not in {r.sku for r in db.list_sku_cost_rows(s)} else "/sku-costs", status_code=303)


@app.post("/base-products/rename")
def rename_base_product(s: Db, old: Annotated[str, Form()], new: Annotated[str, Form()], unit_label: Annotated[str, Form()] = ""):
    db.rename_base_product(s, old=old.strip(), new=new.strip(), unit_label=unit_label.strip())
    s.commit()
    return RedirectResponse("/sku-costs", status_code=303)


@app.post("/listing-maps/delete")
def remove_listing_map(s: Db, sku: Annotated[str, Form()]):
    db.delete_listing_map(s, sku.strip())
    s.commit()
    return RedirectResponse("/sku-costs", status_code=303)


@app.post("/sku-costs")
def add_sku_cost(s: Db, sku: Annotated[str, Form()], product_name: Annotated[str, Form()], unit_cost: Annotated[str, Form()], effective_from: Annotated[date, Form()]):
    db.insert_sku_cost(s, sku=sku.strip(), product_name=product_name.strip(), unit_cost=parse_money(unit_cost), effective_from=effective_from)
    s.commit()
    return RedirectResponse("/sku-costs", status_code=303)


@app.get("/sku-costs/{cost_id}/edit", response_class=HTMLResponse)
def edit_sku_cost_form(request: Request, s: Db, cost_id: int, error: str | None = None):
    row = db.get_sku_cost(s, cost_id)
    if row is None:
        return RedirectResponse("/sku-costs", status_code=303)
    return _render(request, "sku_cost_edit.html", row=row, error=error)


@app.post("/sku-costs/{cost_id}/edit")
def edit_sku_cost(s: Db, cost_id: int, sku: Annotated[str, Form()], product_name: Annotated[str, Form()], unit_cost: Annotated[str, Form()],
                  effective_from: Annotated[date, Form()]):
    try:
        db.update_sku_cost(s, cost_id, sku=sku.strip(), product_name=product_name.strip(), unit_cost=parse_money(unit_cost), effective_from=effective_from)
        s.commit()
    except IntegrityError:
        s.rollback()
        return RedirectResponse(f"/sku-costs/{cost_id}/edit?error=duplicate", status_code=303)
    except ValueError:
        s.rollback()
        return RedirectResponse(f"/sku-costs/{cost_id}/edit?error=money", status_code=303)
    return RedirectResponse("/sku-costs", status_code=303)


@app.post("/sku-costs/{cost_id}/delete")
def remove_sku_cost(s: Db, cost_id: int):
    db.delete_sku_cost(s, cost_id)
    s.commit()
    return RedirectResponse("/sku-costs", status_code=303)


@app.get("/expenses", response_class=HTMLResponse)
def expenses(request: Request, s: Db):
    return _render(request, "expenses.html", rows=db.list_expense_rows(s), today=date.today())


@app.post("/expenses")
def add_expense(s: Db, kind: Annotated[str, Form()], platform: Annotated[str, Form()], amount: Annotated[str, Form()],
                incurred_on: Annotated[date, Form()], note: Annotated[str, Form()] = ""):
    db.insert_expense(s, kind=ExpenseKind(kind).value, platform=platform, amount=parse_money(amount), incurred_on=incurred_on, note=note.strip())
    s.commit()
    return RedirectResponse("/expenses", status_code=303)


@app.post("/expenses/{expense_id}/delete")
def remove_expense(s: Db, expense_id: int):
    db.delete_expense(s, expense_id)
    s.commit()
    return RedirectResponse("/expenses", status_code=303)
