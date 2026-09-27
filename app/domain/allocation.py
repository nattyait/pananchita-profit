"""Allocation rule (ADR-0002). The ONLY place shared/platform expenses are split. Pure."""
from __future__ import annotations

from collections.abc import Hashable
from typing import TypeVar

K = TypeVar("K", bound=Hashable)


def split_proportionally[K: Hashable](total: int, weights: dict[K, int]) -> dict[K, int]:
    """Split `total` satang across keys in proportion to weights (largest-remainder rounding).

    Guarantees sum(result) == total when any weight > 0. Rounding leftovers go to the largest weight.
    If all weights are 0 (or empty) nothing can be allocated and {} is returned — the caller keeps the total.
    """
    positive = {k: w for k, w in weights.items() if w > 0}
    total_w = sum(positive.values())
    if total_w == 0:
        return {}
    shares = {k: total * w // total_w for k, w in positive.items()}
    remainder = total - sum(shares.values())
    if remainder:
        biggest = max(positive, key=lambda k: (positive[k], str(k)))
        shares[biggest] += remainder
    return shares
