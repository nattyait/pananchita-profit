"""Flow: the pricing page's expense share equals TikTok's expense share on the profit page (ADR-0002, ADR-0008)."""
from datetime import date, datetime

from app.domain.types import Platform, Settlement
from app.effects import db
from app.orchestration.pricing import PricingRequest, SimulatePrice
from app.orchestration.profit_report import BuildProfitReport

TODAY = date(2026, 9, 29)
DAY = date(2026, 9, 10)


def test_expense_share_includes_own_ads_other_and_share_of_shared():
    s = db.make_session_factory("sqlite:///:memory:")()
    u = db.insert_upload(s, platform="tiktok", kind="income", filename="i.xlsx", sha256="1", uploaded_by="เก๋", uploaded_at=datetime(2026, 9, 29))
    db.insert_settlements(s, u.id, (Settlement(Platform.TIKTOK, "T", DAY, 60000, product_price=80000), Settlement(Platform.SHOPEE, "S", DAY, 40000)))
    db.insert_expense(s, kind="ads", platform="tiktok", amount=6000, incurred_on=DAY, note="")
    db.insert_expense(s, kind="other", platform="tiktok", amount=600, incurred_on=DAY, note="")
    db.insert_expense(s, kind="staff", platform="shared", amount=10000, incurred_on=DAY, note="")  # 60 % → tiktok 6000
    s.commit()

    r = SimulatePrice(s).run(PricingRequest(), today=TODAY)
    tiktok = BuildProfitReport(s).run(start=date(2026, 8, 1), end=TODAY).by_platform["tiktok"]
    assert tiktok.expense_total == 6000 + 600 + 6000
    assert r.rates.expense_bp == round(tiktok.expense_total / tiktok.net_received * 10000) == 2100
    assert r.learned.ads_bp == 1000 and r.learned.other_expense_bp == 1100
