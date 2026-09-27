from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# One env var decides where all persistent data lives (SQLite file + raw uploads).
# Local: ./data · Railway: the mounted volume path, e.g. PNC_DATA_DIR=/data
DATA_DIR = Path(os.environ.get("PNC_DATA_DIR", ROOT / "data"))
DB_URL = os.environ.get("PNC_DB_URL", f"sqlite:///{DATA_DIR / 'app.db'}")
UPLOAD_ROOT = Path(os.environ.get("PNC_UPLOAD_ROOT", DATA_DIR / "uploads"))
CONFIG_ROOT = ROOT / "config" / "platforms"
TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"
