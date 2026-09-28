"""Use case: a staff member uploads one platform report.

Sequence: hash+save raw file → dedupe by sha256 → insert ReportUpload → read rows → find header →
resolve mapping → parse (pure) → insert values → record status/problems. Any exception → status=failed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.domain import mapping
from app.domain.platforms import parser_for
from app.domain.types import Platform, ReportKind
from app.effects import db, file_store, mapping_loader, report_reader

log = logging.getLogger("import")


@dataclass(frozen=True)
class ImportOutcome:
    upload_id: int
    status: str  # imported | failed | duplicate
    row_count: int
    problems: tuple[str, ...]
    error: str = ""


class ImportReport:
    def __init__(self, session: Session, upload_root: Path, config_root: Path, now: datetime | None = None):
        self.s, self.upload_root, self.config_root = session, upload_root, config_root
        self.now = now or datetime.now()

    def run(self, *, platform: Platform, kind: ReportKind, filename: str, data: bytes, uploaded_by: str) -> ImportOutcome:
        sha = file_store.sha256_of(data)
        file_store.save(self.upload_root, sha, filename, data)  # raw file FIRST, before any parsing
        existing = db.find_upload_by_sha(self.s, sha)
        if existing is not None:
            log.info("duplicate upload sha=%s upload_id=%s", sha, existing.id)
            return ImportOutcome(existing.id, "duplicate", existing.row_count, tuple(existing.problems.splitlines()))
        upload = db.insert_upload(self.s, platform=platform.value, kind=kind.value, filename=filename, sha256=sha,
                                  uploaded_by=uploaded_by, uploaded_at=self.now)
        self.s.commit()
        try:
            sheets = report_reader.read_sheets(data, filename)
            spec = mapping.spec_from_yaml(mapping_loader.load_platform_mapping(self.config_root, platform.value), kind.value)
            hit = mapping.find_header(sheets, spec)
            if hit is None:
                raise ValueError("หาแถวหัวคอลัมน์ไม่เจอ — ตรวจว่าเลือกชนิดรายงานถูกและไฟล์มีคอลัมน์ " + ", ".join(spec.required))
            sheet_idx, header_idx = hit
            rows = sheets[sheet_idx]
            resolved = mapping.resolve(rows[header_idx], spec)
            if not resolved.ok:
                raise ValueError("ไฟล์ขาดคอลัมน์ที่จำเป็น: " + ", ".join(resolved.missing_required))
            records = mapping.to_records(rows, header_idx, resolved)
            parser = parser_for(platform)
            if kind is ReportKind.INCOME:
                result = parser.parse_income(records, spec.options)
                count = db.insert_settlements(self.s, upload.id, result.values)
                charges_added = db.insert_charges_if_new(self.s, result.charges)
            elif kind is ReportKind.ADS:
                result = parser.parse_ads(records, spec.options)
                count = charges_added = db.insert_charges_if_new(self.s, result.charges)
            else:
                result = parser.parse_orders(records, spec.options)
                count = db.insert_order_lines(self.s, upload.id, result.values)
                charges_added = 0
            problems = [f"แถว {p.row_no}: {p.message}" if p.row_no else p.message for p in result.problems]
            if kind is ReportKind.ADS:
                seen = len(result.charges) - charges_added
                problems.insert(0, f"นำเข้าค่าแอด {charges_added} รายการ" + (f" (ข้าม {seen} รายการที่เคยนำเข้าแล้ว)" if seen else "") + " — ดูในหน้า ค่าใช้จ่าย")
            elif charges_added:
                problems.insert(0, f"นำเข้าค่าใช้จ่ายที่แพลตฟอร์มหักจากยอดโอน {charges_added} รายการ (ดูในหน้า ค่าใช้จ่าย)")
            db.set_upload_status(self.s, upload.id, status="imported", row_count=count, problems=problems)
            self.s.commit()
            log.info("imported upload_id=%s sha=%s rows=%s problems=%s", upload.id, sha, count, len(problems))
            return ImportOutcome(upload.id, "imported", count, tuple(problems))
        except Exception as exc:  # noqa: BLE001 — recorded on the upload row, never swallowed
            self.s.rollback()
            db.set_upload_status(self.s, upload.id, status="failed", error=str(exc))
            self.s.commit()
            log.exception("import failed upload_id=%s sha=%s", upload.id, sha)
            return ImportOutcome(upload.id, "failed", 0, (), str(exc))
