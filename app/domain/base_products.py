"""Pure rules about BaseProduct lifecycle (ADR-0006)."""
from __future__ import annotations

from collections.abc import Iterable

from app.domain.types import ListingMap


def deletable_base_products(names: Iterable[str], maps: Iterable[ListingMap], order_line_skus: Iterable[str]) -> frozenset[str]:
    """A BaseProduct may be deleted only if nothing prices through it: no ListingMap points at it and no
    OrderLine uses its name as its own ProductKey. Then deleting it (and its SkuCost rows) cannot change any COGS."""
    in_use = {m.base_product for m in maps} | set(order_line_skus)
    return frozenset(n for n in names if n not in in_use)
