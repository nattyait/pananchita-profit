"""Reads config/platforms/<platform>.yaml. Effect (file IO)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_platform_mapping(root: Path, platform: str) -> dict[str, Any]:
    return yaml.safe_load((root / f"{platform}.yaml").read_text(encoding="utf-8"))
