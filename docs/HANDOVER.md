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
- **Statement ingestion, analysis, understanding, region detection, and schema
  discovery (Phase 1+2+3+4+5 — no transaction parser)**: after upload, a Celery
  task (`worker.parse_statement`) downloads the stored file unmodified, then for
  PDFs runs `worker/worker/pdf_analysis.py`'s `analyze_pdf` (via `pdfplumber`) to
  produce a `Page` per page (`worker/worker/document.py` — `width`/`height`/
  `text`/`text_blocks`/`images`) and `is_scanned` to flag `needs_ocr` (a
  scanned/image-only PDF with no real text layer — detection only, no OCR runs).
  When there's real extracted text, `worker/worker/document_understanding.py`'s
  `DocumentUnderstandingService.analyze` then classifies the document
  (bank/credit-card statement, institution, account, currency, period,
  page-ranged sections) via Qwen2.5-VL-7B-Instruct over Hugging Face's Inference
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
  columns). `Statement.page_count`/`parser_version`/`needs_ocr`/`pages`/
  `document_analysis`/`transaction_regions`/`transaction_schema` all get
  persisted (the four JSON-shaped ones as `JSONB`, migrations
  `b2e3d4f5a6c7`/`c3f4a5b6d7e8`/`d4e5f6a7b8c9`/`e5f6a7b8c9d0`), `status`
  becomes `"ingested"` (a scanned PDF, or any AI step failing, still succeeds
  — each is independently best-effort/non-fatal). No transaction-line parser
  exists yet — earlier parsing-pipeline attempts were deleted entirely (never
  committed, so no history to preserve). See [DECISIONS.md](DECISIONS.md)'s
  "Phase 5: transaction schema discovery", "Phase 4: transaction region
  detection", "Phase 3: document understanding", "Persist `Statement.pages`",
  "Phase 2: PDF document analysis", and "Statement parsing scoped down to
  Phase 1" entries, and `worker/worker/tasks.py`'s `# TODO(phase 6): hand
  document (+ document_analysis + transaction_regions + transaction_schema)
  to a real transaction-line parser here.` marker for exactly where the next
  parser plugs in.
- **Viewing extracted text blocks, document classification, detected regions,
  and discovered schema**:
  `GET /api/statements/{id}/pages`, `/analysis`, `/transaction-regions`, and
  `/transaction-schema` (`backend/app/api/statements.py`) return a statement's
  persisted `pages`/`document_analysis`/`transaction_regions`/
  `transaction_schema` (same ownership check as `/view`). Frontend: a "Text
  blocks" link per statement row (`components/statements-list.tsx`, shown for
  `status === "ingested"` PDFs) opens `/statements/analysis`, which renders, top
  to bottom: `components/document-analysis-summary.tsx` (document type/
  institution/account/currency/period + section list, or "Not yet classified"),
  `components/transaction-regions-view.tsx` (page/region table, or an
  explanatory empty state), `components/transaction-schema-view.tsx`
  (target-field → source-column table, or an explanatory empty state), then
  `components/statement-pages-view.tsx` (each page as a collapsible section with
  a table of `text_blocks`). This is a debugging/inspection view, not part of
  the intended end-user product surface — it exists so extraction/
  classification/region/schema quality can be checked against real statements
  before Phase 6 (a real transaction parser) gets built on top of it.
- **Worker**: `worker/` (Celery) has one task (`worker.parse_statement`,
  `worker/worker/tasks.py`, ingestion + analysis + understanding + region
  detection + schema discovery) with its own DB
  access layer (`worker/worker/config.py`, `db.py`, `models.py` — hand-mirrored,
  non-authoritative mappings; Alembic in `backend/` remains the sole schema
  authority). Dependencies: `celery[redis]`, `sqlalchemy`, `psycopg`, `httpx`,
  `pdfplumber`, `python-dotenv`, `pydantic`, `openai` — `pypdf` was retired earlier
  in favor of pdfplumber; `pydantic` was removed then re-added once Phase 3 needed
  schema validation (see [DECISIONS.md](DECISIONS.md)). `openai` is used purely as
  the client inside `worker/worker/ai_provider.py`'s `AIProvider` — a thin wrapper
  over any OpenAI-compatible endpoint, not an OpenAI account. Which provider/model
  actually runs is pure config (`AI_BASE_URL`/`MODEL_API_KEY`/`AI_MODEL`), defaulting
  to Hugging Face's router (OpenRouter was tried first but has no free-tier Qwen
  model at all).
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

- Nothing currently in flight. Last completed unit of work: Phase 5 transaction
  schema discovery — `worker/worker/transaction_schema_discovery.py`'s
  `TransactionSchemaDiscoveryService` figures out what a transaction record
  looks like in a given document (which columns map to `transaction_date`/
  `post_date`/`description`/`amount`/`currency`, `amount` handling
  Debit/Credit-split tables via a list of sources), using the same `AIProvider`
  (`worker/worker/ai_provider.py`, config-driven — `MODEL_PROVIDER` picks
  `OPENROUTER_BASE_URL`/`OPENROUTER_API_KEY` vs. `HUGGINGFACE_BASE_URL`/
  `HUGGINGFACE_API_KEY`, `AI_MODEL` picks the model — no model/provider
  hard-coded in any of the AI services) and the same self-repair-retry/
  best-effort approach as Phases 3–4; persisted on `Statement.transaction_schema`
  (`JSONB`) and viewable via a new `GET /api/statements/{id}/transaction-schema`
  + a table on the `/statements/analysis` page. Best-effort — never fails
  ingestion, and skipped entirely when there are no detected transaction
  regions to examine. No OCR/vision and no transaction-line extraction yet —
  see [DECISIONS.md](DECISIONS.md)'s 2026-08-23 and 2026-08-19 entries. Backend
  (47 tests) and worker (29 tests) pass.
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
- **No transaction-line parser exists.** Every ingested statement lands at
  `status="ingested"` with an empty `transactions` table behind it — this is the
  current, intended state of Phase 1+2+3+4+5, not a bug. The Transactions
  page/API work correctly, they just have nothing to show until Phase 6 (a real
  parser) exists.
- **No OCR/vision exists.** `Statement.needs_ocr` gets set for scanned/image-only
  PDFs, but nothing acts on it yet — flagged only, not processed. Document
  understanding, transaction region detection, and schema discovery are all
  skipped entirely for these too (see above).
- **All three AI steps need `MODEL_API_KEY`** (or the `MODEL_PROVIDER`-specific
  `OPENROUTER_API_KEY`/`HUGGINGFACE_API_KEY` — see `worker/worker/config.py`).
  Without it, every PDF statement ingests fine but `document_analysis`/
  `transaction_regions`/`transaction_schema` all stay `null` forever (a logged
  warning, not a crash). With the default provider (Hugging Face), get a free
  token at hf.co/settings/tokens (with "Make calls to Inference Providers"
  permission) and set it as `HUGGINGFACE_API_KEY` (or `MODEL_API_KEY`) in
  `.env`. To benchmark or swap models/providers, change `MODEL_PROVIDER`/
  `AI_MODEL` (and the matching `<PROVIDER>_API_KEY`) — no code change needed,
  see `worker/worker/ai_provider.py` (all three AI services share it). Also
  worth knowing: the default is a free-tier 7B model, not a frontier one —
  expect it to occasionally misclassify unusual statement formats, leave
  fields `null`, return an imprecise region, or return a plausible-looking but
  wrong schema mapping.
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

- Phase 6: build a real transaction-line parser that consumes the `Document`
  object (`worker/worker/document.py`), its `DocumentAnalysis` classification
  (`worker/worker/document_analysis.py` — which pages hold `transactions`
  sections), its `TransactionRegionDetection` bounding boxes
  (`worker/worker/transaction_regions.py` — exactly where on each of those pages
  to look), *and* its `TransactionSchemaDiscovery` column mapping
  (`worker/worker/transaction_schema.py` — which column is which field) and
  produces `transactions` rows — the seam is marked with a `# TODO(phase 6)`
  comment in `worker/worker/tasks.py`. Not yet scoped/agreed how (deterministic
  vs. LLM-assisted, bank-specific vs. generic) — discuss with the user before
  starting.
- OCR/vision for scanned PDFs (`Statement.needs_ocr=true`) — detection exists,
  nothing consumes the flag yet, and document understanding/region detection/
  schema discovery are all skipped for these too. Also not yet scoped (which
  OCR engine/vision API, whether it produces the same `Page`/`text_blocks`
  shape or something else).
- Run the Docker build once Docker Desktop is available (see "In progress" above) —
  note the worker image will need to build `pydantic`/`openai` now too.
