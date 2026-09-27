"""Platform adapters. Each module exposes parse_income(records) and parse_orders(records)."""
from __future__ import annotations

from types import ModuleType

from app.domain.platforms import shopee
from app.domain.types import Platform

PARSERS: dict[Platform, ModuleType] = {
    Platform.SHOPEE: shopee,
}


def parser_for(platform: Platform) -> ModuleType:
    if platform not in PARSERS:
        raise NotImplementedError(f"no parser for {platform.value}")
    return PARSERS[platform]
