"""Use case: map many listings to BaseProducts at once, starting from suggestions (fetch → decide → act)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.listing_suggestions import ListingMapSuggestion, parse_bulk_rows, suggest_listing_maps
from app.effects import db


@dataclass(frozen=True)
class BulkRow:
    listing: db.ProductSeen
    suggestion: ListingMapSuggestion


class BulkMapListings:
    def __init__(self, session: Session):
        self.s = session

    def rows(self) -> list[BulkRow]:
        seen = db.products_seen(self.s)
        todo = [p for p in seen if not p.base_product and not p.has_cost]
        suggestions = suggest_listing_maps(((p.sku, p.product_name, p.variant_name) for p in todo),
                                           ((p.product_name, p.base_product) for p in seen if p.base_product))
        return [BulkRow(p, suggestions[p.sku]) for p in todo]

    def run(self, rows: list[tuple[str, str, str]]) -> tuple[int, int]:
        """Returns (saved, rows with a BaseProduct but unusable units)."""
        maps, invalid = parse_bulk_rows(rows)
        for m in maps:
            db.upsert_base_product(self.s, name=m.base_product, unit_label="")
            db.upsert_listing_map(self.s, sku=m.sku, base_product=m.base_product, units_per_listing=m.units_per_listing, unit_price=0)
        self.s.commit()
        return len(maps), invalid
