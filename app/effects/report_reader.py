"""xlsx/csv bytes → list of rows (list of cells). No interpretation here."""
from __future__ import annotations

import csv
import io
from typing import Any

import openpyxl


def read_rows(data: bytes, filename: str) -> list[list[Any]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if name.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        return [list(r) for r in csv.reader(io.StringIO(text))]
    raise ValueError("รองรับเฉพาะไฟล์ .xlsx หรือ .csv")
