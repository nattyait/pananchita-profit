"""ListingMapSuggestion (pure): guess BaseProduct and units for listings not yet mapped (ADR-0006).

Shops rename listings with every promotion ("[โปร2แถม2] X" → "[โปร3แถม2] X"), which creates a new ProductKey.
We suggest, never save: the units change with the promotion, so a person confirms every row.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.types import ListingMap

_LEADING_TAG = re.compile(r"^\s*(?:G\.\s*)?[\[(][^\])]*[\])]\s*")
_BUY_GET = re.compile(r"(\d+)\s*แถม\s*(\d+)")
_COMBO = re.compile(r"\d\s*\+")
_COUNT_UNIT = re.compile(r"(\d+)\s*(?:กล่อง|ถุง|ห่อ|หลอด|ชิ้น|ขวด|กระปุก)")
_TRAILING_NUMBER = re.compile(r"(\d+)\s*$")


@dataclass(frozen=True)
class ListingMapSuggestion:
    sku: str
    base_product: str  # "" when no mapped listing shares the title core
    units_per_listing: int | None  # None when the promo text gives no count


def title_core(title: str) -> str:
    """Product title without leading promo tags like "[โปร3แถม2]" or "G.(โปรรวม)"."""
    t = title.strip()
    while True:
        stripped = _LEADING_TAG.sub("", t, count=1)
        if stripped == t:
            break
        t = stripped
    t = t.lstrip()
    while t and unicodedata.category(t[0]) == "Mn":
        t = t[1:]
    return re.sub(r"\s+", " ", t).strip()


def _units_in(text: str, *, trailing: bool) -> int | None:
    if m := _BUY_GET.search(text):
        return int(m.group(1)) + int(m.group(2))
    if _COMBO.search(text):
        return sum(int(n) for n in re.findall(r"\d+", text))
    if m := _COUNT_UNIT.search(text):
        return int(m.group(1))
    if trailing and (m := _TRAILING_NUMBER.search(text)):
        return int(m.group(1))
    return None


def guess_units(title: str, variant: str) -> int | None:
    """Base units per sold piece from the variation, else the title. A guess for a person to confirm."""
    units = _units_in(variant, trailing=True) if variant else None
    if units is None:
        units = _units_in(title, trailing=False)
    return units if units and units > 0 else None


def suggest_listing_maps(unmapped: Iterable[tuple[str, str, str]], mapped: Iterable[tuple[str, str]]) -> dict[str, ListingMapSuggestion]:
    """unmapped: (ProductKey, title, variant). mapped: (title, BaseProduct) of listings already mapped."""
    bases: dict[str, Counter[str]] = {}
    for title, base in mapped:
        bases.setdefault(title_core(title), Counter())[base] += 1
    out = {}
    for sku, title, variant in unmapped:
        counts = bases.get(title_core(title))
        base = min(counts, key=lambda b: (-counts[b], b)) if counts else ""
        out[sku] = ListingMapSuggestion(sku, base, guess_units(title, variant))
    return out


def parse_bulk_rows(rows: Iterable[tuple[str, str, str]]) -> tuple[tuple[ListingMap, ...], int]:
    """(ProductKey, BaseProduct, units text) → maps to save, and how many rows had a BaseProduct but unusable units.
    Rows without a BaseProduct are left for later, not errors."""
    maps: list[ListingMap] = []
    invalid = 0
    for sku, base, units in rows:
        base = base.strip()
        if not base:
            continue
        units = units.strip()
        if units.isdigit() and int(units) >= 1:
            maps.append(ListingMap(sku, base, int(units)))
        else:
            invalid += 1
    return tuple(maps), invalid
