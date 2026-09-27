"""Raw upload storage: bytes in, sha256 + path out. Files are never modified."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(root: Path, sha256: str, filename: str, data: bytes) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    path = root / f"{sha256}{suffix}"
    if not path.exists():
        path.write_bytes(data)
    return path


def load(root: Path, sha256: str, filename: str) -> bytes:
    return (root / f"{sha256}{Path(filename).suffix.lower()}").read_bytes()
