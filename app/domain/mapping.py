"""ColumnMapping resolution: file headers ↔ yaml spec. Pure."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_WS = re.compile(r"\s+")


def normalize(header: object) -> str:
    return _WS.sub(" ", str(header or "")).strip().lower()


@dataclass(frozen=True)
class ReportSpec:
    required: tuple[str, ...]
    headers: dict[str, tuple[str, ...]]  # field → accepted header names
    options: dict[str, Any] = field(default_factory=dict)  # platform-specific data for the parser (e.g. cancelled statuses)


@dataclass(frozen=True)
class ResolvedMapping:
    columns: dict[str, int]  # field → column index in the header row
    missing_required: tuple[str, ...] = ()
    unmapped_headers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.missing_required


def spec_from_yaml(data: dict[str, Any], kind: str) -> ReportSpec:
    report = data["reports"][kind]
    return ReportSpec(
        required=tuple(report["required"]),
        headers={f: tuple(names) for f, names in report["headers"].items()},
        options=dict(report.get("options") or {}),
    )


def find_header_row(rows: list[list[Any]], spec: ReportSpec) -> int | None:
    """Index of the first row containing a header for every required field (exact after normalize)."""
    for idx, row in enumerate(rows):
        cells = {normalize(c) for c in row}
        if all(any(normalize(n) in cells for n in spec.headers[f]) for f in spec.required):
            return idx
    return None


def find_header(sheets: list[list[list[Any]]], spec: ReportSpec) -> tuple[int, int] | None:
    """(sheet index, row index) of the first sheet/row holding every required header. Shopee puts data on sheet 2."""
    for sheet_idx, rows in enumerate(sheets):
        row_idx = find_header_row(rows, spec)
        if row_idx is not None:
            return sheet_idx, row_idx
    return None


def resolve(header_row: list[Any], spec: ReportSpec) -> ResolvedMapping:
    norm = [normalize(h) for h in header_row]
    columns: dict[str, int] = {}
    for fld, names in spec.headers.items():
        for name in names:
            n = normalize(name)
            if n in norm:
                columns[fld] = norm.index(n)
                break
        else:  # prefix match as a fallback, longest accepted name first
            for name in sorted(names, key=len, reverse=True):
                n = normalize(name)
                hit = next((i for i, h in enumerate(norm) if h.startswith(n)), None)
                if hit is not None:
                    columns[fld] = hit
                    break
    used = set(columns.values())
    return ResolvedMapping(
        columns=columns,
        missing_required=tuple(f for f in spec.required if f not in columns),
        unmapped_headers=tuple(str(h) for i, h in enumerate(header_row) if i not in used and normalize(h)),
    )


def to_records(rows: list[list[Any]], header_idx: int, mapping: ResolvedMapping) -> list[tuple[int, dict[str, Any]]]:
    """(1-based row number in file, {field: cell}) for each data row after the header; blank rows dropped."""
    out: list[tuple[int, dict[str, Any]]] = []
    for offset, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if not any(normalize(c) for c in row):
            continue
        rec = {f: (row[i] if i < len(row) else None) for f, i in mapping.columns.items()}
        out.append((offset, rec))
    return out
