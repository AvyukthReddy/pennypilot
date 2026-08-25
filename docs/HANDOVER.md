# Handover

Living snapshot of where PennyPilot stands right now. Read this first, every session.
Update it — don't append to it — as soon as state changes; this is a snapshot, not a log
(use [DECISIONS.md](DECISIONS.md) for history and rationale, [FLOW.md](FLOW.md) for
request-flow maps).

## Where things stand

- **Architecture split**: Next.js Server Actions handle auth only (Supabase); FastAPI
  (`backend/`) handles everything else. See [DECISIONS.md](DECISIONS.md).
- **Auth**: Supabase Auth wired end-to-end — login, signup, logout, password reset,
  email confirm callback. Frontend proxy/middleware (`frontend/src/proxy.ts`,
  `lib/supabase/middleware.ts`) gates access; backend verifies Supabase JWTs
  (`backend/app/core/security.py`).
- **Profile**: `users` table (renamed from `profiles`, adds `created_at`, `updated_at`,
  `profile_image`) lives in Supabase Postgres, managed via SQLAlchemy + Alembic
  (`backend/app/models/user.py`, model class `User`). `GET/PUT /api/profile` exposed
  with CORS — route/schema names still say "profile" (`backend/app/schemas/profile.py`,
  `backend/app/api/profile.py`) since that's the settings-page contract, only the
  underlying table/model was renamed. Frontend account settings page
  (`frontend/src/app/settings/`) reads/writes it through the shared API service layer
  (`frontend/src/services/app.service.ts`, `hooks/use-api-request.ts`).
- **Avatar upload**: `POST /api/profile/image` (`backend/app/api/profile.py`) accepts a
  multipart file, validates type/size in `backend/app/services/storage.py`, and uploads
  to the Supabase Storage `avatars` bucket using the caller's own JWT (forwarded via
  `CurrentUser.token`) — Storage RLS enforces users can only write to their own
  `{user_id}/` folder, same trust model as Postgres RLS. Bucket + RLS policy
  (`avatars_owner_write`) were created directly via SQL against `storage.buckets` /
  `storage.objects` (not tracked by Alembic — that's Supabase-managed schema, see
  [DECISIONS.md](DECISIONS.md)). Frontend UI is the avatar circle + "Change photo" in
  `frontend/src/components/profile-form.tsx`; files over 5MB are compressed client-side
  first (`frontend/src/lib/compress-image.ts`, canvas resize + JPEG re-encode) rather
  than rejected — the backend's 5MB check stays as a safety net for anyone hitting the
  API directly.
- **Statement upload**: `GET/POST/DELETE /api/statements` +
  `GET /api/statements/{id}/view` (`backend/app/api/statements.py`) store uploaded
  bank/credit-card statements (PDF/CSV, 20MB max) in a `statements` table
  (`backend/app/models/statement.py`) and a private Supabase Storage `statements`
  bucket (RLS policy `statements_owner_all`), same trust model as avatars — see
  [DECISIONS.md](DECISIONS.md). Viewing a file goes through a short-lived (120s)
  Supabase signed URL (`get_statement_view_url` in `services/storage.py`) since the
  bucket is private, unlike avatars' public URL. Frontend page at
  `frontend/src/app/statements/` (`components/statements-list.tsx`), linked from the
  navbar. Uploads are deduplicated by SHA-256 (`Statement.file_hash`) — re-uploading
  the same file for the same user returns `409`.
- **Statement ingestion, analysis, understanding, region detection, schema
  discovery, transaction extraction, verification, financial validation,
  recovery, and confidence (Phase 1+2+3+4+5+6+7+8+9+10)**: after upload, a Celery
  task (`worker.parse_statement`) downloads the stored file unmodified, then for
  PDFs runs `worker/worker/pdf_analysis.py`'s `analyze_pdf` (via `pdfplumber`) to
  produce a `Page` per page (`worker/worker/document.py` — `width`/`height`/
  `text`/`text_blocks`/`images`) and `is_scanned` to flag `needs_ocr` (a
  scanned/image-only PDF with no real text layer — detection only, no OCR runs).
  When there's real extracted text, `worker/worker/document_understanding.py`'s
  `DocumentUnderstandingService.analyze` then classifies the document
  (bank/credit-card statement, institution, account, currency, period,
  beginning/ending balance, page-ranged sections) via Qwen2.5-VL-7B-Instruct
  over Hugging Face's Inference
  Providers router (free tier), validated against the closed `DocumentAnalysis`
  Pydantic schema (`worker/worker/document_analysis.py`) with one self-repair
  retry on invalid JSON — best-effort, never fails the statement. When that
  classification found a `"transactions"` section,
  `worker/worker/transaction_region_detection.py`'s
  `TransactionRegionDetectionService.detect` then narrows those specific pages
  down to an exact `[x0, y0, x1, y1]` bounding region each — same `AIProvider`,
  same retry/best-effort approach, validated against `TransactionRegionDetection`
  (`worker/worker/transaction_regions.py`). When any regions were detected,
  `worker/worker/transaction_schema_discovery.py`'s
  `TransactionSchemaDiscoveryService.discover` then figures out what a
  transaction actually looks like in this document — crops each page's
  `text_blocks` down to just its detected region, and maps whatever columns
  it finds onto `Transaction`'s fixed fields (`transaction_date`/`post_date`/
  `description`/`amount`/`currency`), validated against the closed
  `TransactionSchemaDiscovery` schema (`worker/worker/transaction_schema.py`,
  `amount` a list to support tables that split it across Debit/Credit
  columns). Finally, `worker/worker/transaction_extraction.py`'s
  `TransactionExtractionService.extract` runs once per detected region (not
  once per document) — each call crops that page's `text_blocks` down to its
  region (shared `_blocks_in_region` helper, now in `worker/worker/_regions.py`)
  and is prompted with the Phase 5 column mapping, producing every
  transaction row on that page, validated against the closed
  `TransactionExtraction` schema (`worker/worker/extracted_transactions.py`
  — `transaction_date`/`post_date`/`description`/`amount`/`currency` only,
  no category, no prose). Immediately after each region's extraction,
  `worker/worker/transaction_verification.py`'s
  `TransactionVerificationService.verify` checks it against that same
  region's content plus its own extracted JSON, for missing/duplicate
  transactions, wrong dates/amounts/signs, and split-or-merged multi-line
  rows — validated against the closed `TransactionVerification` schema
  (`worker/worker/verification_issues.py`). When invalid,
  `TransactionExtractionService.extract` is called again for that region
  with the issues as correction feedback, and that retry's output is what
  actually gets persisted (trusted either way, not re-verified). Finally,
  once the region loop finishes, `worker/worker/financial_validation.py`'s
  `validate_transactions` — a plain Python function, no AI call — runs once
  over the entire final transaction list: date sanity, amount sanity,
  duplicate detection, and (only when `document_analysis` states both a
  beginning and ending balance) arithmetic reconciliation
  (`beginning_balance + sum(all signed amounts) == ending_balance`). When
  that fails with a `balance_mismatch`, `worker/worker/recovery.py`'s
  `attempt_recovery` re-extracts one region at a time (most-suspect first —
  regions with no successful Phase-7 verification record) and re-validates
  after each, stopping on the first candidate that reconciles; every
  candidate tried lands in `FinancialValidation.recovery_attempts`
  (`page`/`succeeded`) regardless of outcome, and it's the final
  (post-recovery, if any ran) row set that actually gets inserted. Finally,
  gated on the same condition as region detection,
  `worker/worker/confidence.py`'s `compute_confidence`, also plain Python,
  no AI call, combines extraction completeness, verification cleanliness,
  financial-validation issue count, balance reconciliation (including
  whether recovery was needed), and structural consistency (did every
  flagged page get a detected region) into one equally-weighted (`0.2`
  each) `score` and a `status` (`validated`/`needs_review`/`unreliable`,
  its own vocabulary, never touches `Statement.status`).
  `Statement.page_count`/`parser_version`/
  `needs_ocr`/`pages`/`document_analysis`/`transaction_regions`/
  `transaction_schema`/`transaction_verification`/`financial_validation`/
  `confidence` all
  get persisted (the seven JSON-shaped ones as `JSONB`, migrations
  `b2e3d4f5a6c7`/`c3f4a5b6d7e8`/`d4e5f6a7b8c9`/`e5f6a7b8c9d0`/
  `f6a7b8c9d0e1`/`a7b8c9d0e1f2`/`b8c9d0e1f2a3`, `recovery_attempts` is a
  new key inside the existing `financial_validation` blob, no migration of
  its own),
  `status` becomes `"ingested"` (a scanned
  PDF, or any AI step failing, still succeeds — each is independently
  best-effort/non-fatal, and extraction/verification are best-effort *per
  region*, so one page failing doesn't discard another page's
  already-extracted transactions; financial validation, recovery, and
  confidence are purely diagnostic/corrective and never touch `status`
  either way), and
  every successfully extracted
  (and possibly corrected/recovered) row is inserted into the `transactions` table
  (`worker/worker/models.py`'s `TransactionRow`). Earlier parsing-pipeline
  attempts were deleted entirely (never committed, so no history to
  preserve). See [DECISIONS.md](DECISIONS.md)'s "Phase 10: confidence",
  "Phase 9: recovery", "Phase
  8: deterministic financial validation", "Phase 7: transaction
  verification", "Phase
  6: transaction extraction", "Phase 5: transaction schema discovery", "Phase
  4: transaction region detection", "Phase 3: document understanding",
  "Persist `Statement.pages`", "Phase 2: PDF document analysis", and
  "Statement parsing scoped down to Phase 1" entries.
- **Viewing confidence, extracted text blocks, document classification, detected regions,
  discovered schema, verification report, and financial validation**:
  `GET /api/statements/{id}/pages`, `/analysis`, `/transaction-regions`,
  `/transaction-schema`, `/transaction-verification`,
  `/financial-validation`, and `/confidence` (`backend/app/api/statements.py`) return a
  statement's persisted `pages`/`document_analysis`/`transaction_regions`/
  `transaction_schema`/`transaction_verification`/`financial_validation`/
  `confidence`
  (same ownership check as `/view`). Frontend: a
  "Text blocks" link per statement row (`components/statements-list.tsx`,
  shown for `status === "ingested"` PDFs) opens `/statements/analysis`, which
  renders, top to bottom: `components/confidence-view.tsx` (first, a
  colored status pill, score percentage, warnings, and a five-component
  breakdown, or an explanatory empty state), `components/document-analysis-summary.tsx`
  (document type/institution/account/currency/period/beginning and ending
  balance + section list, or "Not
  yet classified"), `components/transaction-regions-view.tsx` (page/region
  table, or an explanatory empty state), `components/transaction-schema-view.tsx`
  (target-field → source-column table, or an explanatory empty state),
  `components/transactions-view.tsx` (a date/description/amount table of
  every persisted `TransactionRow` for the statement, via the same
  `GET /api/transactions?statement_id=...` the standalone `/transactions`
  page uses, or an explanatory empty state),
  `components/transaction-verification-view.tsx` ("all verified", a
  type/page/description issue table, or an explanatory empty state),
  `components/financial-validation-view.tsx` ("all checks passed", a
  type/description issue table plus a balance reconciliation breakdown, plus
  a one-line recovery note when `recovery_attempts` is non-empty, or
  an explanatory empty state), then
  `components/statement-pages-view.tsx` (each page as a collapsible section with
  a table of `text_blocks`). This is a debugging/inspection view, not part of
  the intended end-user product surface — it exists so extraction/
  classification/region/schema/verification/validation quality can be
  checked against real statements.
- **Worker**: `worker/` (Celery) has one task (`worker.parse_statement`,
  `worker/worker/tasks.py`, ingestion + analysis + understanding + region
  detection + schema discovery + transaction extraction + verification +
  financial validation + recovery + confidence) with
  its own DB
  access layer (`worker/worker/config.py`, `db.py`, `models.py` — hand-mirrored,
  non-authoritative mappings; Alembic in `backend/` remains the sole schema
  authority). Dependencies: `celery[redis]`, `sqlalchemy`, `psycopg`, `httpx`,
  `pdfplumber`, `python-dotenv`, `pydantic`, `openai`, `Pillow` — `pypdf` was retired
  earlier in favor of pdfplumber; `pydantic` was removed then re-added once Phase 3
  needed schema validation; `Pillow` was already pdfplumber's own transitive
  dependency, made explicit once `worker/worker/_regions.py` started importing
  `PIL.Image` directly to crop rendered page images (see [DECISIONS.md](DECISIONS.md)).
  `openai` is used purely as the client inside `worker/worker/ai_provider.py`'s
  `AIProvider` — a thin wrapper over any OpenAI-compatible endpoint, not an OpenAI
  account. Which provider/model actually runs is pure config
  (`AI_BASE_URL`/`MODEL_API_KEY`/`AI_MODEL`), defaulting to Hugging Face's router
  (OpenRouter was tried first but has no free-tier Qwen model at all).
- **Shared**: `shared/shared/schemas/transaction.py` (`ParsedTransaction`) is left in
  place but **unused** — no service currently depends on it. It's a plausible starting
  point for whatever contract the next parser needs, not active code. The Docker
  repo-root build context that existed solely to let the worker image reach it was
  reverted (`docker/docker-compose.yml`, `worker/Dockerfile` back to
  `context: ../worker`); the root `.dockerignore` that went with it was removed too.
- **Postgres RLS**: `users`, `statements`, and `transactions` all have Row Level
  Security enabled with an `auth.uid() = user_id` owner policy (`alembic_version` has
  RLS on with no policy, fully locking it out of the API). This closes a real gap
  Supabase's Security Advisor flagged — without it, the public
  `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` could read/write any user's rows directly via
  PostgREST, bypassing FastAPI's own auth entirely. See [DECISIONS.md](DECISIONS.md)'s
  2026-08-18 entry. **Any new per-user table must get RLS + an owner policy in the
  same pass that creates it.**

## In progress

- Nothing currently in flight. Last completed unit of work: editable
  statement currency. New `Statement.currency` column (`String(3)`,
  nullable, migration `c9d0e1f2a3b4`) is a user override, separate from
  `document_analysis.currency` (AI-detected). `GET/PATCH
  /api/statements/{id}/currency` resolves the effective value as override,
  then detected, then a `"USD"` default, and returns which of the three
  (`source`) it picked; `PATCH` with `{"currency": null}` clears the
  override back to auto-detect. Every amount on `/statements/analysis`
  (transaction rows, both balance summaries) now renders through
  `frontend/src/lib/format-currency.ts`, which maps common codes to a
  symbol and falls back to `"<code> <amount>"` for the rest, so nothing
  shows a bare number. `components/currency-context.tsx`'s
  `CurrencyProvider` fetches the effective currency once per page load and
  shares it via context so every section stays in sync after an edit,
  instead of each re-fetching independently. `components/
  currency-editor.tsx` is a dropdown (not free text, to keep the value a
  real currency code) sourced from `format-currency.ts`'s
  `SUPPORTED_CURRENCIES` list, with a "Reset to auto-detected" action when
  overridden. The analysis page also gained two section titles it was
  missing ("Document analysis", "Raw data"), matching every other section.
  See [DECISIONS.md](DECISIONS.md)'s 2026-08-25 "Statement currency"
  entry. Worker unaffected. Backend: `.venv/Scripts/python.exe -m pytest
  -q` passes (69 tests), migration applied, ruff clean. Frontend: `tsc
  --noEmit` and `eslint src/` both clean.
- **Docker build not verified**: `docker compose config` validates, but Docker Desktop
  hasn't been running in this environment, so `docker compose build worker` has not
  actually been run. Do that before relying on the containerized stack. (The
  repo-root build context that existed for `shared/` is gone now, so this build
  should be simpler/faster than it would have been earlier in this project's history.)

## Known broken / rough edges

- Profile image upload (`POST /api/profile/image`) hasn't been exercised against a real
  logged-in browser session yet — only unit-tested (auth mocked, `upload_avatar`
  monkeypatched). Worth a manual pass through the settings page before considering it
  done.
- **No dedup/idempotency guard on statement reprocessing.** Re-running
  `worker.parse_statement` on an already-`"ingested"` statement inserts a
  second set of `transactions` rows rather than replacing the first — the
  JSONB columns already overwrite cleanly on reprocessing, `transactions`
  rows don't yet. Not currently a problem since nothing triggers
  reprocessing, but worth fixing before that becomes a feature.
- **No OCR/vision exists.** `Statement.needs_ocr` gets set for scanned/image-only
  PDFs, but nothing acts on it yet — flagged only, not processed. Document
  understanding, transaction region detection, schema discovery, extraction,
  verification, financial validation (no transactions to check),
  recovery (nothing to validate, so nothing to recover from), and
  confidence (same gating as region detection, nothing to score) are all
  skipped entirely for these too (see above).
- **All five AI steps need `MODEL_API_KEY`** (or the `MODEL_PROVIDER`-specific
  `OPENROUTER_API_KEY`/`HUGGINGFACE_API_KEY` — see `worker/worker/config.py`).
  Without it, every PDF statement ingests fine but `document_analysis`/
  `transaction_regions`/`transaction_schema`/`transaction_verification` all
  stay `null` forever and no `transactions` rows get inserted (a logged
  warning, not a crash). With the default provider (Hugging Face), get a free
  token at hf.co/settings/tokens (with "Make calls to Inference Providers"
  permission) and set it as `HUGGINGFACE_API_KEY` (or `MODEL_API_KEY`) in
  `.env`. To benchmark or swap models/providers, change `MODEL_PROVIDER`/
  `AI_MODEL` (and the matching `<PROVIDER>_API_KEY`) — no code change needed,
  see `worker/worker/ai_provider.py` (all five AI services share it). Also
  worth knowing: the default is a free-tier 7B model, not a frontier one —
  expect it to occasionally misclassify unusual statement formats, leave
  fields `null`, return an imprecise region, a plausible-looking but wrong
  schema mapping, miss/misread some rows during extraction, or return a
  plausible-looking but wrong verification verdict (i.e. verification itself
  isn't infallible — it's a best-effort second opinion, not ground truth).
- **`REDIS_URL` in `.env` (`redis://redis:6379/0`) is a Docker Compose service
  hostname — it only resolves inside Docker's network.** Running the backend or the
  Celery worker locally (outside Docker, e.g. `uvicorn --reload` / `poetry run celery`
  as most of this project's local dev has been done) needs
  `$env:REDIS_URL = "redis://localhost:6379/0"` set in that shell first, or enqueueing
  silently fails (`getaddrinfo failed`, swallowed by `upload_statement_file`'s
  `except Exception: pass`) and statements sit stuck at `status="uploaded"` forever.
  `DATABASE_URL` doesn't have this problem — `worker/worker/config.py` now
  auto-loads it from the root `.env` (see [DECISIONS.md](DECISIONS.md)), matching how
  the backend already worked. Redis itself can be started standalone via
  `docker compose -f docker/docker-compose.yml up -d redis` (maps to `localhost:6379`)
  without needing to run the rest of the stack in Docker.

## What to avoid

- Don't put business logic in Next.js Server Actions — auth only. Everything else goes
  through FastAPI. (See [DECISIONS.md](DECISIONS.md) for why.)
- Don't assume Next.js APIs match training data — this repo is on Next.js 16 with
  breaking changes; check `frontend/node_modules/next/dist/docs/` first.

## Next up

- OCR/vision for scanned PDFs (`Statement.needs_ocr=true`) — detection exists,
  nothing consumes the flag yet, and document understanding/region detection/
  schema discovery/extraction/verification/financial validation/recovery/
  confidence are
  all skipped for these too. Also
  not yet scoped (which OCR engine/vision API, whether it produces the same
  `Page`/`text_blocks` shape or something else).
- Transaction categorization (AI/merchant-based) and a full transaction-editing
  UI. The `transactions` table now actually gets populated, checked,
  self-corrected, and scored for confidence (Phase 6+7+8+9+10), so this is
  the natural next
  consumer-facing feature.
- Dedup/idempotency guard on statement reprocessing — see "Known broken" above.
- Surfacing `financial_validation`/`transaction_verification`/`confidence`
  somewhere a real user would see them (not just the debug
  `/statements/analysis` view) — e.g. a warning badge on the statements list
  — once there's a concrete product need for it.
- Recovery is currently scoped to `balance_mismatch` only (see
  [DECISIONS.md](DECISIONS.md)'s 2026-08-24 "Phase 9" entry for why) — if
  the other `FinancialValidationIssue` types ever need the same kind of
  self-correction, that's a separate design question (they already point at
  a specific transaction, not a whole region).
- The five confidence-component weights are equal (`0.2` each) by
  deliberate default, not tuned against any real-world outcome data; worth
  revisiting once there's a corpus of real statements to check the score
  against.
- Run the Docker build once Docker Desktop is available (see "In progress" above) —
  note the worker image will need to build `pydantic`/`openai` now too.
