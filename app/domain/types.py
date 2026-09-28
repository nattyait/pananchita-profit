"""Domain value types. Names follow CONTEXT.md exactly. Money is integer satang."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TypeVar


class Platform(StrEnum):
    SHOPEE = "shopee"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"


SHARED = "shared"  # Expense not tied to one Platform


class ReportKind(StrEnum):
    ORDERS = "orders"
    INCOME = "income"


class ExpenseKind(StrEnum):
    ADS = "ads"
    STAFF = "staff"
    TAX = "tax"
    OTHER = "other"


@dataclass(frozen=True)
class Settlement:
    """Money the platform actually released for one order on one settled_at. The only revenue source."""

    platform: Platform
    order_id: str
    settled_at: date
    net_received: int  # satang, as reported by the platform — never recomputed
    product_price: int = 0
    seller_discount: int = 0
    commission_fee: int = 0
    service_fee: int = 0
    transaction_fee: int = 0
    affiliate_fee: int = 0
    tax_fee: int = 0
    platform_fee: int = 0
    ads_fee: int = 0  # ad-credit top-up deducted from the payout ("ค่าธรรมเนียมเติมเงินโฆษณาจากเงิน Escrow")
    shipping_fee_diff: int = 0  # buyer-paid + platform subsidy + charged in seller's name (normally 0)
    other_adjustment: int = 0

    @property
    def settlement_key(self) -> tuple[str, str, date]:
        return (self.platform.value, self.order_id, self.settled_at)


@dataclass(frozen=True)
class OrderLine:
    platform: Platform
    order_id: str
    line_no: int
    sku: str  # ProductKey: SKU, or "product | variant" when the shop sets no SKU (ADR-0003)
    quantity: int
    ordered_at: date
    product_name: str = ""
    status: str = ""
    payment_method: str = ""
    cancelled: bool = False
    variant_name: str = ""  # effective variation after default-variation stripping (display only; ProductKey is `sku`)
    line_amount: int = 0  # satang: unit price × quantity from the order report — a weight for splitting, never revenue (ADR-0004)


@dataclass(frozen=True)
class SkuCost:
    sku: str
    unit_cost: int  # satang
    effective_from: date


@dataclass(frozen=True)
class Expense:
    kind: ExpenseKind
    platform: str  # Platform value or SHARED
    amount: int  # satang
    incurred_on: date
    note: str = ""
    id: int | None = None
    source_ref: str = ""  # "<platform>:<transaction id>" for charges imported from an income statement (ADR-0005); empty when typed by staff


@dataclass(frozen=True)
class ImportProblem:
    message: str
    row_no: int | None = None
    field: str | None = None


T = TypeVar("T")


@dataclass(frozen=True)
class ParseResult[T]:
    values: tuple[T, ...]
    problems: tuple[ImportProblem, ...]
    charges: tuple[Expense, ...] = ()  # platform charges found in an income statement (ADR-0005)
