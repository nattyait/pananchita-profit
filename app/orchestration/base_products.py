"""Use case: delete a BaseProduct that nothing prices through (fetch → decide → act)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.base_products import deletable_base_products
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
