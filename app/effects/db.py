"""SQLAlchemy models + dumb read/write functions. Money columns are integer satang.

report_uploads content and settlements/order_lines are append-only. The only UPDATE in this file is the
upload *status* (received → imported/failed), which is bookkeeping, not content.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, and_, create_engine, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.domain.types import Expense, ExpenseKind, OrderLine, Platform, Settlement, SkuCost


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


class SkuCostRow(Base):
    __tablename__ = "sku_costs"
    __table_args__ = (UniqueConstraint("sku", "effective_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(255), index=True)  # ProductKey
    product_name: Mapped[str] = mapped_column(String(255), default="")
    unit_cost: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date)


class ExpenseRow(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    incurred_on: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(255), default="")


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
    "order_lines": {
        "product_name": "VARCHAR(255) NOT NULL DEFAULT ''", "status": "VARCHAR(80) NOT NULL DEFAULT ''",
        "payment_method": "VARCHAR(80) NOT NULL DEFAULT ''", "cancelled": "BOOLEAN NOT NULL DEFAULT 0",
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
                           payment_method=ln.payment_method, cancelled=ln.cancelled))
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
                           bool(r.cancelled)) for r in s.scalars(q))


# ---------- sku costs ----------
def all_sku_costs(s: Session) -> tuple[SkuCost, ...]:
    return tuple(SkuCost(r.sku, r.unit_cost, r.effective_from) for r in s.scalars(select(SkuCostRow)))


def list_sku_cost_rows(s: Session) -> list[SkuCostRow]:
    return list(s.scalars(select(SkuCostRow).order_by(SkuCostRow.sku, SkuCostRow.effective_from.desc())))


def insert_sku_cost(s: Session, *, sku: str, product_name: str, unit_cost: int, effective_from: date) -> SkuCostRow:
    row = SkuCostRow(sku=sku, product_name=product_name, unit_cost=unit_cost, effective_from=effective_from)
    s.add(row)
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


def known_skus_without_cost(s: Session) -> list[tuple[str, str]]:
    have = {r.sku for r in s.scalars(select(SkuCostRow))}
    seen: dict[str, str] = {}
    for r in s.scalars(select(OrderLineRow)):
        seen.setdefault(r.sku, r.product_name)
    return sorted((sku, name) for sku, name in seen.items() if sku not in have)


# ---------- expenses ----------
def all_expenses(s: Session) -> tuple[Expense, ...]:
    return tuple(Expense(ExpenseKind(r.kind), r.platform, r.amount, r.incurred_on, r.note, r.id) for r in s.scalars(select(ExpenseRow)))


def list_expense_rows(s: Session) -> list[ExpenseRow]:
    return list(s.scalars(select(ExpenseRow).order_by(ExpenseRow.incurred_on.desc(), ExpenseRow.id.desc())))


def insert_expense(s: Session, *, kind: str, platform: str, amount: int, incurred_on: date, note: str) -> ExpenseRow:
    row = ExpenseRow(kind=kind, platform=platform, amount=amount, incurred_on=incurred_on, note=note)
    s.add(row)
    s.flush()
    return row


def delete_expense(s: Session, expense_id: int) -> None:
    row = s.get(ExpenseRow, expense_id)
    if row is not None:
        s.delete(row)
        s.flush()
