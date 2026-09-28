"""Pure rules about BaseProduct lifecycle (ADR-0006)."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.domain.profit import effective_cost
from app.domain.types import ListingMap, SkuCost


def deletable_base_products(names: Iterable[str], maps: Iterable[ListingMap], order_line_skus: Iterable[str]) -> frozenset[str]:
    """A BaseProduct may be deleted only if nothing prices through it: no ListingMap points at it and no
    OrderLine uses its name as its own ProductKey. Then deleting it (and its SkuCost rows) cannot change any COGS."""
    in_use = {m.base_product for m in maps} | set(order_line_skus)
    return frozenset(n for n in names if n not in in_use)


def merge_refusal(source: str, target: str, names: Iterable[str], unmapped_order_line_skus: Iterable[str]) -> str | None:
    """Why merging source into target is not allowed, or None. An unmapped ProductKey equal to the source name
    prices through the source's own SkuCost rows directly, so the source cannot disappear."""
    known = set(names)
    if source == target:
        return "same"
    if source not in known or target not in known:
        return "unknown"
    if source in set(unmapped_order_line_skus):
        return "used_as_product_key"
    return None


def merge_changes_cogs(source_costs: Sequence[SkuCost], target_costs: Sequence[SkuCost]) -> bool:
    """After a merge the source's listings price through the target. COGS changes only if both have costs and
    they differ on some effective date (a target without costs takes over the source's rows instead)."""
    if not source_costs or not target_costs:
        return False
    src, tgt = tuple(source_costs), tuple(target_costs)
    s_key, t_key = src[0].sku, tgt[0].sku
    dates = {c.effective_from for c in src} | {c.effective_from for c in tgt}
    return any(effective_cost(src, s_key, d) != effective_cost(tgt, t_key, d) for d in dates)
