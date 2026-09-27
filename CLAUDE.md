# Pananchita Profit — CLAUDE.md

Web app that tells the Pananchita (ปนันชิตา) team whether each order — and each period — is actually profitable,
using ONLY money the platform really released (cash basis). Python 3.12 · FastAPI · SQLAlchemy 2 · SQLite · Jinja2.
This file is a behavioral contract. Every rule here changes how you act.
Full reasoning lives in docs/domain_design.md — read it before structural changes.
Domain glossary: @CONTEXT.md · ADRs: docs/adr/

## Stack & Commands
- FastAPI + Jinja2 (server-rendered, no JS framework), SQLAlchemy 2 + SQLite (`data/app.db`), openpyxl for .xlsx.
  Runs on one machine or one small VM; no queue, no background jobs (uploads are small and synchronous).
- `make test` (= `pytest -q`) — run before claiming any task done
- `make lint` (= `ruff check .`) — must pass; do not add `# noqa` without a comment explaining why
- `make run` — starts the app at http://localhost:8000

## Architecture (non-negotiable)
- Functional Core / Imperative Shell (see Code Structure). Three folders, three kinds of code. No fourth kind.
- Platforms (Shopee, TikTok, Facebook) are **adapters**: one parser module per platform in `app/domain/platforms/`
  plus one column-mapping file in `config/platforms/`. Everything downstream (profit, reports, DB) speaks only
  the platform-neutral terms in CONTEXT.md (Settlement, OrderLine, …). Domain code never branches on a
  platform name — because the moment `profit.py` says `if platform == "shopee"`, adding TikTok means editing
  the profit engine, and a profit bug then hides behind a platform condition.
- The web layer (`app/web/`) only: parses HTTP input → calls one orchestration use case → renders a template.
  No SQL, no arithmetic, no business `if` in routes or templates — because those are untestable there.
- No module may import "upward": domain imports nothing from effects/orchestration/web; effects import domain
  only; orchestration imports domain + effects; web imports orchestration only. Cycles are forbidden.

## Domain Rules
- **IMPORTANT: Revenue is recognised ONLY from a Settlement (ยอดรับจริง) — the amount the platform actually
  released, net of commission, service/transaction fees and affiliate commission.** Never derive revenue from
  an order's product price. Why: COD orders and cancellations mean the order report over-states cash for weeks;
  the owner asked for "ยอดรับจริงเท่านั้น" so the number on screen must be money that reached the bank.
- **IMPORTANT: `report_uploads`, `settlements` and `order_lines` are append-only. Never UPDATE or DELETE their
  content.** To correct a bad upload, upload a corrected file; the newest upload for the same key wins at read
  time (`db._latest_upload_per_key`). The only UPDATE allowed is the upload's own status/problems bookkeeping.
  Why: these tables are the audit trail that lets anyone reconcile the screen against the bank statement.
- Raw upload file is persisted (bytes + sha256) BEFORE any parsing. Never parse-then-save. Why: if a parser
  bug is found later we must be able to re-run every historical file.
- A period P&L is filtered by `settled_at` (วันที่ปล่อยเงิน), NEVER by `ordered_at`. Why: the owner wants to
  see profit in the period the money arrived; an order placed in March but paid in April is April revenue.
- `ordered_at` vs `settled_at` vs `uploaded_at` are three different timestamps and are never conflated.
- Imports are idempotent two ways: the same file (sha256) is never imported twice, and the read model keys are
  `settlement_key = (platform, order_id, settled_at)` and `(platform, order_id, line_no)` for order lines.
  Several income lines for one order on one settled_at are summed into ONE Settlement by the parser.
- Money is stored as integer satang (`amount_satang`), parsed via `Decimal` — never `float`. Why: 0.1+0.2.
- COGS for an order uses the SKU cost that was effective on `ordered_at` (effective-dated cost table), not the
  latest cost. Why: cost changes must not rewrite last month's profit.
- Shared expenses (staff, tax, misc without a platform) are allocated to platforms and orders by their share
  of net received in the period. The rule lives in ONE pure function (`domain/allocation.py`) — see ADR-0002.
- COGS is keyed by ProductKey (SKU, or "ชื่อสินค้า | ชื่อตัวเลือก" when the shop sets no SKU — ADR-0003). Never key by
  product name alone: two variants of one product have different costs.
- Platform status words ("ยกเลิกแล้ว", "Cancelled") are translated to `OrderLine.cancelled` inside the platform parser,
  driven by the yaml. Domain code never compares status strings — that is a platform concept.
- Schema changes are additive only (ADD COLUMN with a default) and applied in `db.make_session_factory`. Never rename
  or drop a column: the SQLite file on the Railway volume is the only copy of the data.
- Anything the parser could not map or parse is reported to the user as an import problem; it is never
  silently skipped or defaulted to zero. Why: a zero fee looks like profit.

## Trust Invariants (structural, not config)
- **IMPORTANT: The profit screen has no code path that reads `product_price` as revenue.** The read model
  (`ProfitReport`) is built from `Settlement` objects only; `OrderLine` contributes quantities/SKU for COGS.
- An order that has order lines but no settlement is shown as "รอรับเงิน" (pending), never as revenue 0
  and never omitted. Why: staff must see money still owed by the platform.
- Every uploaded file is downloadable again exactly as uploaded (bytes + sha256 match).

## Data & Privacy
- Reports contain customer names/addresses/phones. Those columns are NOT mapped, NOT stored in the DB, and
  NOT logged; only the raw file keeps them, in `data/uploads/`, outside the web root.
- No login in v1 (LAN/internal use). Every upload records `uploaded_by` (free-text staff name) — required.
- Deletion request: delete the raw file by sha256 from `data/uploads/`; DB rows hold no personal data.

## Ubiquitous Language
The single source of truth for all domain terms is @CONTEXT.md — use those exact terms in code, comments and
migrations; no synonyms. Before introducing ANY new domain term it goes through a structured review first —
check against existing terms, question edge cases, confirm no collision — then add it to CONTEXT.md. Never add
a term straight from one conversation without that pass.

## Code Structure: Functional Core, Imperative Shell
- **Pure logic** → `app/domain/`. Decisions only. Same input, same output. No DB/file/network/`datetime.now()`.
- **Side effects** → `app/effects/`. Dumb by design: receive a command, do it, return a value. No business `if`.
- **Orchestration** → `app/orchestration/`. One class per use case: fetch (effect) → decide (pure) → act (effect).
When implementing a feature, state which of the three kinds each new file is.

## Testing Strategy
- Pure logic → unit tests in `tests/domain/`, exhaustive, no mocks/DB. These tests ARE the spec.
  Test-first: tests exist and are owner-approved BEFORE implementation.
- Side effects → thin integration tests on an in-memory SQLite, one happy path per effect.
- Orchestration → few flow tests, stub effects, assert sequence.
- End-to-end → one happy path per user-facing flow (upload → see profit).
- A bug found in production ALWAYS becomes a unit test first, then gets fixed.

## Code Style
- Dataclasses (`frozen=True`) for domain values; SQLAlchemy models only in `app/effects/db.py`.
- User-facing text is Thai and lives in templates, never in domain code.
- Never modify an existing invariant test to make code pass.
- Column mappings are data (`config/platforms/*.yaml`), never hard-coded header strings in Python.

## Operational Quality
- Every import logs `upload_id`, `sha256`, row counts, problem counts — never row contents.
- Exceptions during import are stored on the upload row (`status=failed`, `error`), never swallowed.
- Backup: copy `data/` nightly to the shop's shared drive; restore drill = restore to a laptop, open the app,
  compare last month's total with the bank. Owner does this monthly.

## Workflow
- Every change goes through issue → branch → PR → merge. Never push directly to main.
- Before merging, remind the user to review the PR — silence is not approval. Merge only on an explicit
  instruction (e.g. "merge เลย"); never self-merge proactively.
- Adding a platform = new parser + new mapping yaml + tests. If it needs a change in `domain/profit.py`,
  stop: that is an architecture decision → ADR first.
- Every architecture decision (new module dependency, core pattern change, structural rework) creates or
  updates an ADR in `docs/adr/` in the same PR.
