"""Use cases on BaseProducts: delete an unused one, rename, merge one into another (fetch → decide → act)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.base_products import deletable_base_products, merge_changes_cogs, merge_refusal
from app.domain.profit import effective_cost
from app.domain.types import SkuCost
from app.effects import db


class DeleteUnusedBaseProduct:
    def __init__(self, session: Session):
        self.s = session

    def deletable(self) -> frozenset[str]:
        names = [b.name for b in db.list_base_products(self.s)]
        return deletable_base_products(names, db.all_listing_maps(self.s), db.all_order_line_skus(self.s))

    def run(self, name: str) -> bool:
        if name not in self.deletable():
            return False
        db.delete_base_product(self.s, name)
        self.s.commit()
        return True


@dataclass(frozen=True)
class MergePreview:
    refusal: str | None
    changes_cogs: bool
    source_unit_cost: int | None  # latest, for display
    target_unit_cost: int | None
    listing_count: int


class MergeBaseProducts:
    def __init__(self, session: Session):
        self.s = session

    def _costs(self, name: str) -> list[SkuCost]:
        return [c for c in db.all_sku_costs(self.s) if c.sku == name]

    @staticmethod
    def _latest(costs: list[SkuCost]) -> int | None:
        return effective_cost(tuple(costs), costs[0].sku, max(c.effective_from for c in costs)) if costs else None

    def preview(self, source: str, target: str) -> MergePreview:
        names = [b.name for b in db.list_base_products(self.s)]
        maps = db.all_listing_maps(self.s)
        refusal = merge_refusal(source, target, names, db.all_order_line_skus(self.s) - {m.sku for m in maps})
        src, tgt = self._costs(source), self._costs(target)
        listings = sum(1 for m in maps if m.base_product == source)
        return MergePreview(refusal, merge_changes_cogs(src, tgt), self._latest(src), self._latest(tgt), listings)

    def run(self, source: str, target: str, *, confirmed: bool) -> str:
        """"merged", "confirm" when COGS would change and the user has not confirmed, or the refusal reason."""
        p = self.preview(source, target)
        if p.refusal:
            return p.refusal
        if p.changes_cogs and not confirmed:
            return "confirm"
        db.merge_base_product(self.s, source=source, target=target, move_costs=p.target_unit_cost is None)
        self.s.commit()
        return "merged"


class RenameBaseProduct:
    def __init__(self, session: Session):
        self.s = session

    def run(self, *, old: str, new: str, unit_label: str) -> str:
        """"renamed", or "merge" when the new name already belongs to another BaseProduct."""
        if new != old and any(b.name == new for b in db.list_base_products(self.s)):
            return "merge"
        db.rename_base_product(self.s, old=old, new=new, unit_label=unit_label)
        self.s.commit()
        return "renamed"
