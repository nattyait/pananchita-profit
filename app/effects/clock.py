"""Wall clock (effect). Instants are stored as naive UTC; the shop's calendar day is Thai time."""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

SHOP_TZ = ZoneInfo("Asia/Bangkok")


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def today_local() -> date:
    return datetime.now(SHOP_TZ).date()
