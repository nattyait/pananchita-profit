"""Use case: build the ProfitReport for a period (and optional platform)."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domain.missing_reports import MissingReport, missing_reports
from app.domain.profit import ProfitReport, build_report
from app.domain.types import Platform
from app.effects import db


class BuildProfitReport:
    def __init__(self, session: Session):
        self.s = session

    def run(self, *, start: date, end: date, platform: Platform | None = None) -> ProfitReport:
        settlements = db.all_settlement_keys(self.s)  # all dates: needed to decide PendingOrder
        in_period = db.settlements_between(self.s, start, end)  # full fee detail for the period
        keys = {s.settlement_key for s in in_period}
        merged = tuple(in_period) + tuple(s for s in settlements if s.settlement_key not in keys)
        return build_report(
            period_start=start, period_end=end, settlements=merged,
            order_lines=db.all_order_lines(self.s), sku_costs=db.all_sku_costs(self.s),
            expenses=db.all_expenses(self.s), platform=platform, listing_maps=db.all_listing_maps(self.s),
        )

    @staticmethod
    def reports_to_export(report: ProfitReport, today: date) -> tuple[MissingReport, ...]:
        return missing_reports(report.orders, report.pending, today)
