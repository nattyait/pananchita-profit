"""xlsx/csv bytes → sheets, each a list of rows (list of cells). No interpretation here.

Full (non read-only) load on purpose: Shopee files carry a wrong dimension tag and read-only mode then
returns a single row (ADR-0003).
"""
from __future__ import annotations

import csv
import io
from typing import Any

import openpyxl


def read_sheets(data: bytes, filename: str) -> list[list[list[Any]]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        return [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
    if name.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        return [[list(r) for r in csv.reader(io.StringIO(text))]]
    raise ValueError("รองรับเฉพาะไฟล์ .xlsx หรือ .csv")
