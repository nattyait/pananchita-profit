from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.environ.get("PNC_DB_URL", f"sqlite:///{ROOT / 'data' / 'app.db'}")
UPLOAD_ROOT = Path(os.environ.get("PNC_UPLOAD_ROOT", ROOT / "data" / "uploads"))
CONFIG_ROOT = ROOT / "config" / "platforms"
TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"
