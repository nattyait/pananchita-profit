"""SQLAlchemy models + dumb read/write functions. Money columns are integer satang.

report_uploads content and settlements/order_lines are append-only. The only UPDATE in this file is the
upload *status* (received → imported/failed), which is bookkeeping, not content.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, and_, create_engine, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.domain.types import Expense, ExpenseKind, ListingMap, OrderLine, Platform, Settlement, SkuCost


class Base(DeclarativeBase):
    pass


class ReportUploadRow(Base):
    __tablename__ = "report_uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    uploaded_by: Mapped[str] = mapped_column(String(80))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="received")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    problem_count: Mapped[int] = mapped_column(Integer, default=0)
    problems: Mapped[str] = mapped_column(Text, default="")  # one per line, for the UI
    error: Mapped[str] = mapped_column(Text, default="")


class SettlementRow(Base):
    __tablename__ = "settlements"
    __table_args__ = (UniqueConstraint("upload_id", "platform", "order_id", "settled_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("report_uploads.id"))
    platform: Mapped[str] = mapped_column(String(16), index=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    settled_at: Mapped[date] = mapped_column(Date, index=True)
    net_received: Mapped[int] = mapped_column(Integer)
    product_price: Mapped[int] = mapped_column(Integer, default=0)
    seller_discount: Mapped[int] = mapped_column(Integer, default=0)
    commission_fee: Mapped[int] = mapped_column(Integer, default=0)
    service_fee: Mapped[int] = mapped_column(Integer, default=0)
    transaction_fee: Mapped[int] = mapped_column(Integer, default=0)
    affiliate_fee: Mapped[int] = mapped_column(Integer, default=0)
    tax_fee: Mapped[int] = mapped_column(Integer, default=0)
    platform_fee: Mapped[int] = mapped_column(Integer, default=0)
    ads_fee: Mapped[int] = mapped_column(Integer, default=0)
    shipping_fee_diff: Mapped[int] = mapped_column(Integer, default=0)
    other_adjustment: Mapped[int] = mapped_column(Integer, default=0)


class OrderLineRow(Base):
    __tablename__ = "order_lines"
    __table_args__ = (UniqueConstraint("upload_id", "platform", "order_id", "line_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("report_uploads.id"))
    platform: Mapped[str] = mapped_column(String(16), index=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str] = mapped_column(String(255))  # ProductKey
    product_name: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[int] = mapped_column(Integer)
    ordered_at: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(80), default="")
    payment_method: Mapped[str] = mapped_column(String(80), default="")
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    line_amount: Mapped[int] = mapped_column(Integer, default=0)
    variant_name: Mapped[str] = mapped_column(String(255), default="")


class SkuCostRow(Base):
    __tablename__ = "sku_costs"
    __table_args__ = (UniqueConstraint("sku", "effective_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(255), index=True)  # ProductKey
    product_name: Mapped[str] = mapped_column(String(255), default="")
    unit_cost: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date)


class BaseProductRow(Base):
    __tablename__ = "base_products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    unit_label: Mapped[str] = mapped_column(String(40), default="ชิ้น")


class ListingMapRow(Base):
    __tablename__ = "listing_maps"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(255), unique=True)  # ProductKey
    base_product: Mapped[str] = mapped_column(String(255), index=True)
    units_per_listing: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[int] = mapped_column(Integer, default=0)  # satang, display only


class ExpenseRow(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    incurred_on: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    source_ref: Mapped[str] = mapped_column(String(80), default="", index=True)


def make_session_factory(url: str) -> sessionmaker[Session]:
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return sessionmaker(engine, expire_on_commit=False)


# Additive columns only (ADR-0003): name → SQL type + default. create_all never alters existing tables.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "settlements": {
        "product_price": "INTEGER NOT NULL DEFAULT 0", "seller_discount": "INTEGER NOT NULL DEFAULT 0",
        "commission_fee": "INTEGER NOT NULL DEFAULT 0", "service_fee": "INTEGER NOT NULL DEFAULT 0",
        "transaction_fee": "INTEGER NOT NULL DEFAULT 0", "affiliate_fee": "INTEGER NOT NULL DEFAULT 0",
        "tax_fee": "INTEGER NOT NULL DEFAULT 0", "platform_fee": "INTEGER NOT NULL DEFAULT 0", "ads_fee": "INTEGER NOT NULL DEFAULT 0",
        "shipping_fee_diff": "INTEGER NOT NULL DEFAULT 0", "other_adjustment": "INTEGER NOT NULL DEFAULT 0",
    },
    "expenses": {"source_ref": "VARCHAR(80) NOT NULL DEFAULT ''"},
    "order_lines": {
        "product_name": "VARCHAR(255) NOT NULL DEFAULT ''", "status": "VARCHAR(80) NOT NULL DEFAULT ''",
        "payment_method": "VARCHAR(80) NOT NULL DEFAULT ''", "cancelled": "BOOLEAN NOT NULL DEFAULT 0", "line_amount": "INTEGER NOT NULL DEFAULT 0",
        "variant_name": "VARCHAR(255) NOT NULL DEFAULT ''",
    },
}


def _add_missing_columns(engine) -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


# ---------- uploads ----------
def find_upload_by_sha(s: Session, sha256: str) -> ReportUploadRow | None:
    return s.scalar(select(ReportUploadRow).where(ReportUploadRow.sha256 == sha256))


def insert_upload(s: Session, *, platform: str, kind: str, filename: str, sha256: str, uploaded_by: str, uploaded_at: datetime) -> ReportUploadRow:
    row = ReportUploadRow(platform=platform, kind=kind, filename=filename, sha256=sha256, uploaded_by=uploaded_by, uploaded_at=uploaded_at)
    s.add(row)
    s.flush()
    return row


def set_upload_status(s: Session, upload_id: int, *, status: str, row_count: int = 0, problems: list[str] | None = None, error: str = "") -> None:
    row = s.get(ReportUploadRow, upload_id)
    assert row is not None
    row.status, row.row_count, row.error = status, row_count, error
    row.problems = "\n".join(problems or [])
    row.problem_count = len(problems or [])


def list_uploads(s: Session) -> list[ReportUploadRow]:
    return list(s.scalars(select(ReportUploadRow).order_by(ReportUploadRow.id.desc())))


def get_upload(s: Session, upload_id: int) -> ReportUploadRow | None:
    return s.get(ReportUploadRow, upload_id)


# ---------- settlements / order lines ----------
def insert_settlements(s: Session, upload_id: int, settlements: tuple[Settlement, ...]) -> int:
    for st in settlements:
        s.add(SettlementRow(upload_id=upload_id, platform=st.platform.value, order_id=st.order_id, settled_at=st.settled_at,
                            net_received=st.net_received, product_price=st.product_price, seller_discount=st.seller_discount,
                            commission_fee=st.commission_fee, service_fee=st.service_fee, transaction_fee=st.transaction_fee,
                            affiliate_fee=st.affiliate_fee, tax_fee=st.tax_fee, platform_fee=st.platform_fee, ads_fee=st.ads_fee,
                            shipping_fee_diff=st.shipping_fee_diff, other_adjustment=st.other_adjustment))
    s.flush()
    return len(settlements)


def insert_order_lines(s: Session, upload_id: int, lines: tuple[OrderLine, ...]) -> int:
    for ln in lines:
        s.add(OrderLineRow(upload_id=upload_id, platform=ln.platform.value, order_id=ln.order_id, line_no=ln.line_no, sku=ln.sku,
                           product_name=ln.product_name, quantity=ln.quantity, ordered_at=ln.ordered_at, status=ln.status,
                           payment_method=ln.payment_method, cancelled=ln.cancelled, line_amount=ln.line_amount, variant_name=ln.variant_name))
    s.flush()
    return len(lines)


def _latest_upload_per_key(s: Session, model, key_cols):
    """Newest upload wins for the same key (append-only correction rule)."""
    latest = select(*key_cols, func.max(model.upload_id).label("upload_id")).group_by(*key_cols).subquery()
    conds = [getattr(model, c.key) == getattr(latest.c, c.key) for c in key_cols] + [model.upload_id == latest.c.upload_id]
    return select(model).join(latest, and_(*conds))


def settlements_between(s: Session, start: date, end: date) -> tuple[Settlement, ...]:
    m = SettlementRow
    q = _latest_upload_per_key(s, m, [m.platform, m.order_id, m.settled_at]).where(m.settled_at.between(start, end))
    return tuple(
        Settlement(Platform(r.platform), r.order_id, r.settled_at, r.net_received, r.product_price, r.seller_discount, r.commission_fee,
                   r.service_fee, r.transaction_fee, r.affiliate_fee, r.tax_fee, r.platform_fee, r.ads_fee, r.shipping_fee_diff, r.other_adjustment)
        for r in s.scalars(q)
    )


def all_settlement_keys(s: Session) -> tuple[Settlement, ...]:
    """Every settlement regardless of date (needed to decide PendingOrder)."""
    m = SettlementRow
    q = _latest_upload_per_key(s, m, [m.platform, m.order_id, m.settled_at])
    return tuple(Settlement(Platform(r.platform), r.order_id, r.settled_at, r.net_received) for r in s.scalars(q))


def all_order_lines(s: Session) -> tuple[OrderLine, ...]:
    m = OrderLineRow
    q = _latest_upload_per_key(s, m, [m.platform, m.order_id, m.line_no])
    return tuple(OrderLine(Platform(r.platform), r.order_id, r.line_no, r.sku, r.quantity, r.ordered_at, r.product_name, r.status, r.payment_method,
                           bool(r.cancelled), r.variant_name, r.line_amount) for r in s.scalars(q))


# ---------- sku costs ----------
def all_sku_costs(s: Session) -> tuple[SkuCost, ...]:
    return tuple(SkuCost(r.sku, r.unit_cost, r.effective_from) for r in s.scalars(select(SkuCostRow)))


def list_sku_cost_rows(s: Session) -> list[SkuCostRow]:
    return list(s.scalars(select(SkuCostRow).order_by(SkuCostRow.sku, SkuCostRow.effective_from.desc())))


def insert_sku_cost(s: Session, *, sku: str, product_name: str, unit_cost: int, effective_from: date) -> SkuCostRow:
    """Upsert on (sku, effective_from): saving the same product for the same date replaces that date's cost."""
    row = s.scalar(select(SkuCostRow).where(SkuCostRow.sku == sku, SkuCostRow.effective_from == effective_from))
    if row is None:
        row = SkuCostRow(sku=sku, product_name=product_name, unit_cost=unit_cost, effective_from=effective_from)
        s.add(row)
    else:
        row.unit_cost = unit_cost
        if product_name:
            row.product_name = product_name
    s.flush()
    return row


def get_sku_cost(s: Session, cost_id: int) -> SkuCostRow | None:
    return s.get(SkuCostRow, cost_id)


def update_sku_cost(s: Session, cost_id: int, *, sku: str, product_name: str, unit_cost: int, effective_from: date) -> SkuCostRow | None:
    row = s.get(SkuCostRow, cost_id)
    if row is None:
        return None
    row.sku, row.product_name, row.unit_cost, row.effective_from = sku, product_name, unit_cost, effective_from
    s.flush()
    return row


def delete_sku_cost(s: Session, cost_id: int) -> None:
    row = s.get(SkuCostRow, cost_id)
    if row is not None:
        s.delete(row)
        s.flush()


@dataclass(frozen=True)
class ProductSeen:
    """A ProductKey seen in order lines, for the cost page (display only)."""

    sku: str
    platform: str
    product_name: str
    variant_name: str
    quantity: int
    order_count: int
    last_ordered_at: date
    has_cost: bool
    base_product: str = ""
    units_per_listing: int = 0
    unit_price: int = 0


def _variant_from_key(sku: str, product_name: str) -> str:
    """Display text when variant_name is empty: the variation inside a 'name | variant' ProductKey, else the seller SKU
    itself (shops like TikTok put the flavor only in the SKU, so listings with one product name look identical)."""
    if product_name and sku.startswith(product_name + " | "):
        return sku[len(product_name) + 3 :]
    return "" if sku == product_name else sku


def products_seen(s: Session) -> list[ProductSeen]:
    have = {r.sku for r in s.scalars(select(SkuCostRow))}
    maps = {r.sku: r for r in s.scalars(select(ListingMapRow))}
    m = OrderLineRow
    q = _latest_upload_per_key(s, m, [m.platform, m.order_id, m.line_no]).where(m.cancelled.is_(False))
    acc: dict[str, list] = {}
    for r in s.scalars(q):
        variant = r.variant_name or _variant_from_key(r.sku, r.product_name)
        a = acc.setdefault(r.sku, [r.platform, r.product_name, variant, 0, set(), r.ordered_at])
        a[3] += r.quantity
        a[4].add(r.order_id)
        a[5] = max(a[5], r.ordered_at)
    out = []
    for sku, a in acc.items():
        m = maps.get(sku)
        covered = (m.base_product in have) if m else (sku in have)
        out.append(ProductSeen(sku, a[0], a[1], a[2], a[3], len(a[4]), a[5], covered, m.base_product if m else "", m.units_per_listing if m else 0, m.unit_price if m else 0))
    return sorted(out, key=lambda p: (p.has_cost, -p.quantity, p.sku))


# ---------- base products / listing maps (ADR-0006) ----------
def all_listing_maps(s: Session) -> tuple[ListingMap, ...]:
    return tuple(ListingMap(r.sku, r.base_product, r.units_per_listing, r.unit_price) for r in s.scalars(select(ListingMapRow)))


def list_base_products(s: Session) -> list[BaseProductRow]:
    return list(s.scalars(select(BaseProductRow).order_by(BaseProductRow.name)))


def upsert_base_product(s: Session, *, name: str, unit_label: str) -> BaseProductRow:
    row = s.scalar(select(BaseProductRow).where(BaseProductRow.name == name))
    if row is None:
        row = BaseProductRow(name=name, unit_label=unit_label or "ชิ้น")
        s.add(row)
    elif unit_label:
        row.unit_label = unit_label
    s.flush()
    return row


def upsert_listing_map(s: Session, *, sku: str, base_product: str, units_per_listing: int, unit_price: int) -> ListingMapRow:
    row = s.scalar(select(ListingMapRow).where(ListingMapRow.sku == sku))
    if row is None:
        row = ListingMapRow(sku=sku, base_product=base_product, units_per_listing=units_per_listing, unit_price=unit_price)
        s.add(row)
    else:
        row.base_product, row.units_per_listing, row.unit_price = base_product, units_per_listing, unit_price
    s.flush()
    return row


def rename_base_product(s: Session, *, old: str, new: str, unit_label: str) -> None:
    """Rename a base product everywhere it is referenced (maps + cost rows keyed by its name)."""
    row = s.scalar(select(BaseProductRow).where(BaseProductRow.name == old))
    if row is None:
        return
    row.name, row.unit_label = new, unit_label or row.unit_label
    for m in s.scalars(select(ListingMapRow).where(ListingMapRow.base_product == old)):
        m.base_product = new
    for c in s.scalars(select(SkuCostRow).where(SkuCostRow.sku == old)):
        c.sku = new
        if c.product_name == old:
            c.product_name = new
    s.flush()


def delete_listing_map(s: Session, sku: str) -> None:
    row = s.scalar(select(ListingMapRow).where(ListingMapRow.sku == sku))
    if row is not None:
        s.delete(row)
        s.flush()


def all_order_line_skus(s: Session) -> frozenset[str]:
    """Every ProductKey ever imported, cancelled lines included."""
    return frozenset(s.scalars(select(OrderLineRow.sku).distinct()))


def delete_base_product(s: Session, name: str) -> None:
    """Remove a BaseProduct and the SkuCost rows keyed by its name."""
    for row in s.scalars(select(SkuCostRow).where(SkuCostRow.sku == name)):
        s.delete(row)
    for row in s.scalars(select(BaseProductRow).where(BaseProductRow.name == name)):
        s.delete(row)
    s.flush()


# ---------- expenses ----------
def all_expenses(s: Session) -> tuple[Expense, ...]:
    return tuple(Expense(ExpenseKind(r.kind), r.platform, r.amount, r.incurred_on, r.note, r.id, r.source_ref) for r in s.scalars(select(ExpenseRow)))


def list_expense_rows(s: Session) -> list[ExpenseRow]:
    return list(s.scalars(select(ExpenseRow).order_by(ExpenseRow.incurred_on.desc(), ExpenseRow.id.desc())))


def insert_expense(s: Session, *, kind: str, platform: str, amount: int, incurred_on: date, note: str) -> ExpenseRow:
    row = ExpenseRow(kind=kind, platform=platform, amount=amount, incurred_on=incurred_on, note=note)
    s.add(row)
    s.flush()
    return row


def insert_charges_if_new(s: Session, charges: tuple[Expense, ...]) -> int:
    """Insert imported platform charges whose source_ref is not stored yet. Returns how many were added."""
    refs = [c.source_ref for c in charges if c.source_ref]
    existing = set(s.scalars(select(ExpenseRow.source_ref).where(ExpenseRow.source_ref.in_(refs)))) if refs else set()
    added = 0
    for c in charges:
        if c.source_ref in existing:
            continue
        s.add(ExpenseRow(kind=c.kind.value, platform=c.platform, amount=c.amount, incurred_on=c.incurred_on, note=c.note, source_ref=c.source_ref))
        existing.add(c.source_ref)
        added += 1
    s.flush()
    return added


def delete_expense(s: Session, expense_id: int) -> None:
    row = s.get(ExpenseRow, expense_id)
    if row is not None:
        s.delete(row)
        s.flush()
