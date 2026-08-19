# Decisions

Append-only log of meaningful decisions and the reasoning behind them. Code shows what
changed; this shows why. New entries go at the top. Don't edit or delete past entries
when a decision is later reversed — add a new entry that supersedes it and link back.

## 2026-08-19 — Phase 3: document understanding (AIProvider abstraction, Qwen2.5-VL-7B via Hugging Face by default, supersedes pydantic removal)

Answers "what is this document?" — not a transaction extraction. New
`worker/worker/document_understanding.py`'s `DocumentUnderstandingService.analyze
(document) -> DocumentAnalysis` feeds each page's already-extracted `text` (from
Phase 2, not `text_blocks`/coordinates — classification doesn't need layout) to an
LLM and gets back a **closed Pydantic schema**
(`worker/worker/document_analysis.py`): `document_type` (a `Literal`), institution,
account type/last4, currency, statement period, and `sections` (page ranges by
content type, `type` also a closed `Literal`) — never arbitrary JSON.

**No hard-coded model or provider.** `worker/worker/ai_provider.py`'s `AIProvider`
wraps any OpenAI-compatible chat completions endpoint — `base_url`/`api_key`/
`model` all come from `AIProviderConfig`, built from three env vars
(`AI_BASE_URL`/`MODEL_API_KEY`/`AI_MODEL`, `worker.config.default_ai_provider_config`).
`DocumentUnderstandingService` takes an `AIProvider` (constructor-injected,
defaulting to the configured one) rather than building a model client itself —
benchmarking or swapping models/providers is an env change, never a code change to
`document_understanding.py`'s extraction pipeline. The `openai` Python package is
used purely as the OpenAI-compatible HTTP client; no OpenAI account involved.

**Default: Qwen2.5-VL-7B-Instruct via Hugging Face's Inference Providers router**
(`AI_BASE_URL=https://router.huggingface.co/v1`, `AI_MODEL=Qwen/Qwen2.5-VL-7B-
Instruct:featherless-ai`, needs `MODEL_API_KEY` — a free Hugging Face access token
with "Make calls to Inference Providers" permission) — the user's explicit choice,
prioritizing $0 inference cost. OpenRouter was tried first but has no free-tier
Qwen model at all (confirmed against its live `/api/v1/models` catalog — the 7B VL
variant isn't even listed anymore, and no other Qwen model there has a `:free`
tier); Hugging Face's own router does serve this exact model, through the
`featherless-ai` provider (confirmed via
`https://huggingface.co/api/models/Qwen/Qwen2.5-VL-7B-Instruct?expand[]=inferenceProviderMapping`).
The `:featherless-ai` suffix pins that provider explicitly rather than HF's default
`:fastest` auto-selection. This is only the _default_ — any of the three env vars
can be overridden independently to point at a different provider/model entirely.

**Prompt-based JSON + Pydantic validation with one self-repair retry**, not native
structured-output/tool-calling. A free 7B model behind a routing layer isn't
guaranteed to honor `response_format`/forced tool-use as reliably as a frontier
model. On invalid JSON (or a response wrapped in a ` ```json ` fence, which small
models commonly do despite instructions not to), the service re-prompts once with
the validation error and asks for a corrected response before raising
`DocumentUnderstandingError`.

**Best-effort, non-fatal.** By the time this runs, ingestion and Phase 2 analysis
have already succeeded — a classification failure (missing API key, network error,
model never returns valid JSON) must not flip `Statement.status` to `"failed"`; it
just leaves `document_analysis` as `null`, same philosophy as `needs_ocr` detection.
Skipped entirely (not even attempted) when `needs_ocr=true` or a PDF has no
extracted pages — feeding near-empty text would just produce garbage; understanding
a scanned statement waits for the eventual OCR/vision pass, still unbuilt.

**Persisted as `Statement.document_analysis`** (nullable `JSONB`, migration
`c3f4a5b6d7e8`), same pattern as `pages` — exposed via a new
`GET /api/statements/{id}/analysis` (not folded into `StatementRead`, same
reasoning as `/pages`) and shown as a summary card on the existing
`/statements/analysis` page, above the text-blocks viewer that page already had.

**Supersedes the 2026-08-18 entry that removed `pydantic` from `worker/`** (dropped
along with `pypdf`/`shared/` when parsing was rescoped to Phase 1, on the grounds
that nothing used it). This feature genuinely needs schema validation for LLM
output — the removal predates that need. `worker/worker/document_analysis.py`
defines its own copy of the schema rather than reviving a `shared/` dependency or
importing from `backend/`, same decoupling precedent as `worker/worker/models.py`
hand-mirroring the backend's SQLAlchemy models.

## 2026-08-19 — Fix empty-state flash: move `hasFetchedOnce` into `useApiRequest` as `hasSettled`

The `hasFetchedOnce` pattern each list component hand-rolled (`statements-list.tsx`,
`transactions-list.tsx`, `recent-activity.tsx`, `statement-pages-view.tsx`) was meant
to stop "No X found" from flashing before the first fetch resolves — but it still
flashed. Root cause: React Strict Mode double-invokes effects on mount in dev (by
design, to catch exactly this class of bug), which fires the data-fetch effect twice.
`services/app.service.ts`'s `getResponseAsync` aborts the first in-flight request once
the second one starts (same dedup key) — but `useApiRequest.run()`'s
`finally { setLoading(false) }` and each caller's `.then(() => setHasFetchedOnce(true))`
fired **unconditionally**, even for that now-superseded first call. Its `.then()` ran
with `data` still `undefined`, setting `hasFetchedOnce=true` while `statements`/
`transactions`/`pages` were still empty — showing the empty-state message before the
real (second) request had even resolved.

Fixed at the root: `useApiRequest` (`frontend/src/hooks/use-api-request.ts`) now tracks
a `latestCallId` ref, bumped on every `run()` call. A call only touches `loading`/
`error`/`status`/the new `hasSettled` state if it's still the latest call when it
finishes — a superseded call (any call that isn't currently the latest) returns
`undefined` without touching any of them. `hasSettled` replaces every component's local
`hasFetchedOnce`: true once a non-superseded call has settled (success or failure) at
least once. This is a general correctness fix, not dev-only — the same clobbering could
happen in production from any rapid re-fetch (fast filter changes, quick re-navigation),
Strict Mode's double-invoke just makes it reliably reproducible on every single page
load in dev.

## 2026-08-19 — Persist `Statement.pages` (supersedes "pages stay in-memory only")

The 2026-08-19 Phase 2 entry below originally kept `Document.pages` in-memory only,
reasoning nothing downstream consumed it yet. The user wanted to actually inspect
extraction quality against real statements, and asked for it to be visible in the UI
— a real consumer now exists (a person, checking the analysis worked), so that
reasoning no longer holds. `statements.pages` is now a nullable `JSONB` column
(migration `b2e3d4f5a6c7`), populated in `worker/worker/tasks.py` via
`[dataclasses.asdict(page) for page in pages]` right alongside `needs_ocr`/
`page_count`. CSVs get `pages=[]`, same as before.

Exposed via a new `GET /api/statements/{id}/pages` (`backend/app/api/statements.py`,
same ownership check as `/view`) — deliberately **not** folded into `StatementRead`
(used by the statements list), since a multi-page PDF's full text-block list is much
larger than the rest of that response and the list view has no use for it. Frontend:
`frontend/src/components/statement-pages-view.tsx`, reachable via a new "Text blocks"
link per statement row (shown only for `status === "ingested"` PDFs — CSVs have no
pages, and unfinished/failed statements have nothing to show), rendered at
`/statements/analysis?statement_id=...`. Each page is a collapsible `<details>`
section with page dimensions/counts as the summary and a table of `text_blocks`
(`x`/`y`/`width`/`height`/`text`) — first page open by default, rest collapsed, since
a real statement can run into hundreds of blocks across many pages.

`images` (bounding boxes) are persisted too, since they're already part of the `Page`
dataclass, but nothing in the UI surfaces them yet — no consumer for those specifically.

## 2026-08-19 — Phase 2: PDF document analysis (pdfplumber, in-memory Document IR, needs_ocr detection)

Phase 1 left `worker/worker/document.py`'s `Document` as a flat bytes blob — nothing
looked at what was actually on the page. Phase 2 fills that in: `worker/worker/
pdf_analysis.py`'s `analyze_pdf()` opens each PDF with **pdfplumber** and returns a
`list[Page]` (`worker/worker/document.py`) — per page, `width`/`height`, full `text`,
line-grouped `text_blocks` (via `extract_text_lines()`, which already returns
`x0`/`x1`/`top`/`bottom` per line — no hand-rolled word-clustering needed), and
`images` (bounding boxes only, from `page.images` — no pixel bytes extracted, nothing
consumes them yet). `pypdf` is retired; pdfplumber's own page count replaces
`count_pdf_pages`, so the worker carries one PDF library instead of two.

**pdfplumber over PyMuPDF**: PyMuPDF's `get_text("blocks")` is a closer one-line match
for the requested shape and is faster, but it's AGPL-licensed — for a hosted app that
serves users over a network, AGPL's copyleft trigger is a real legal question, not
one to default into silently. pdfplumber (MIT, via pdfminer.six) avoids that, and this
project's earlier — since-deleted — parser attempts already used it, so the extraction
patterns aren't new territory.

**Scanned-PDF detection, not OCR**: `is_scanned()` flags a PDF as `needs_ocr` when its
average extracted characters-per-page falls below a small threshold
(`SCANNED_TEXT_THRESHOLD` in `pdf_analysis.py`) — a cheap, good-enough signal that a
page has no real text layer. Actual OCR/vision is explicitly **not** built this pass;
the user's own framing was that OCR is an "eventually" step once both text and scanned
PDFs need to feed the same downstream `Document` shape. `needs_ocr` is the one new bit
persisted on `Statement` (migration `a1f2c3d4e5b6`, mirrored in `worker/worker/
models.py` per that file's hand-sync convention) — it's a real, useful signal now
(e.g. future UI: "this statement needs OCR, coming soon"), unlike full page/text-block
data, which has no consumer yet.

**`Document.pages` stays in-memory only** — not persisted as JSONB or any new table.
Same reasoning as Phase 1: nothing downstream reads it yet (no parser exists), so
there's nothing to gain from durability beyond what `needs_ocr`/`page_count` already
capture. Add persistence when a real consumer (Phase 3's parser, or a debugging UI)
actually needs to re-read page-level data without re-running analysis.

`INGESTION_VERSION` bumped `"1"` → `"2"` — the analysis logic materially changed, per
the constant's own existing convention (`worker/worker/tasks.py`'s TODO marker moved
from "phase 2" to "phase 3" accordingly).

## 2026-08-18 — Statement parsing scoped down to Phase 1: ingestion only, no parser yet

Two full parsing-pipeline implementations were built and then deleted in the same
session, neither ever committed. The user made a deliberate call to stop iterating on
parser heuristics bank-by-bank and instead scratch all of it, rebuilding from a clean,
explicitly-scoped Phase 1: document **ingestion** only, no parsing. All parsing code
(`worker/worker/parsing/` and its tests/fixtures) was deleted in full.

`worker.parse_statement` now does exactly this: download the file via a short-lived
Supabase signed URL passed as a task argument (never a service-role key — same
caller's-own-JWT trust model as everywhere else, see the avatar-upload entry below;
the worker holds zero standing Supabase credentials) — unchanged, never modified — →
for PDFs, count pages (`pypdf`) → build a `Document` dataclass
(`worker/worker/document.py`) bundling the bytes plus `file_hash`/`size_bytes`/
`page_count`/`parser_version` — the explicit handoff object a future parser will
consume — → persist `page_count`/`parser_version` on the `Statement` row → status
becomes `"ingested"`. `INGESTION_VERSION` is a bumped constant recording which version
of _this_ pipeline touched a document, so a later, smarter ingestion pass can identify
what needs redoing. Worker DB access (`worker/worker/models.py`) is a separate,
hand-mirrored SQLAlchemy mapping, not an import of `backend/app/models` — backend +
Alembic remain the sole schema authority, this trades a small hand-sync burden for
keeping the two services' dependency graphs fully decoupled.

`shared/`'s Poetry path dependency and the Docker repo-root build context that existed
solely to reach it were both reverted — nothing in the worker imports
`shared.schemas.transaction` anymore. `shared/shared/schemas/transaction.py` itself is
left in place (untouched, unused) as a plausible starting point for whatever contract
the next parser needs.

**Deliberately kept, not scratched**: the `transactions` table/model, the
`GET/POST /api/statements` and `GET /api/transactions` APIs, and the frontend
Transactions/statements-list UI. None of that is "a parser" — it's the sink a future
parser will populate. It currently just stays empty, which is honest, not broken.

**How to apply**: the next parsing pass is a clean slate — no obligation to preserve
any part of a prior implementation's module shapes.

## 2026-08-18 — Worker auto-loads root `.env`; `REDIS_URL` there is Docker-network-only

Discovered while trying to run the Celery worker locally (outside Docker) to verify
the parsing pipeline end-to-end: `.env`'s `REDIS_URL=redis://redis:6379/0` uses the
Docker Compose service hostname, which only resolves inside Docker's network —
confirmed via a direct `send_task` call from a local (non-Docker) backend process,
which failed with `getaddrinfo failed` for host `redis`. Every statement uploaded
locally since the parsing feature landed had been silently failing to enqueue (caught
by `upload_statement_file`'s `except Exception: pass`), leaving statements stuck at
`"uploaded"`.

Backend already avoids the analogous `DATABASE_URL` friction because pydantic-settings
loads the root `.env` directly — worker didn't have that, so after making
`DATABASE_URL` a hard-required env var (see the same day's earlier fix, prompted by a
different review comment about the module having a hardcoded fallback connection
string), running the worker locally required manually exporting both `DATABASE_URL`
_and_ `REDIS_URL` every session, which is exactly the kind of friction that gets
skipped and silently breaks things.

Fixed by having `worker/worker/config.py` call `python-dotenv`'s `load_dotenv()` on
the repo-root `.env` (file-path-relative, not cwd-relative, so it works regardless of
where `celery`/`pytest` is invoked from) with the library's default
non-overriding behavior — an already-set shell env var always wins. `REDIS_URL` is
centralized into `config.py` too (`celery_app.py` now imports it from there instead of
its own separate `os.environ.get`), keeping a `redis://localhost:6379/0` fallback
default since that's a reasonable default for genuinely local (no-Docker-at-all) use,
unlike `DATABASE_URL`, which has no sensible generic default.

**Net effect**: `DATABASE_URL` now just works locally with zero setup. `REDIS_URL`
still requires a manual `$env:REDIS_URL = "redis://localhost:6379/0"` override before
starting a local (non-Docker) backend or worker process — that part is inherent to
running some services in Docker and others on the host, not something env-loading can
paper over. Documented in `docs/HANDOVER.md`.

## 2026-08-18 — Enabled Postgres RLS on users/statements/transactions (Supabase Security Advisor finding)

Supabase's Security Advisor flagged `public.users`, `public.statements`,
`public.transactions`, and `public.alembic_version` as "RLS Disabled in Public" —
these tables were exposed via Supabase's auto-generated PostgREST API with no Row
Level Security, while the app's actual access control lived entirely in FastAPI
(JWT verification + `user_id`-scoped queries). Since the frontend ships a public
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, anyone could have called
`https://<project>.supabase.co/rest/v1/<table>` directly with that key and read/
written every user's rows, completely bypassing FastAPI's auth checks — RLS was the
only thing that could have stopped that, and it was off.

Fixed by enabling RLS and adding an `auth.uid() = user_id` owner policy on `users`
(policy compares against `user_id`, that table's actual PK column — not `id`),
`statements`, and `transactions` (mirrors the pattern already used for the `avatars`/
`statements` Storage buckets — `avatars_owner_write`, `statements_owner_all`). Ran as
a one-off script (`backend/scratch_enable_rls.py`, run once via the backend's
superuser-role `DATABASE_URL` which bypasses RLS, then deleted — same "ad hoc SQL for
Supabase-managed/security config, not tracked by Alembic" approach as the Storage
bucket policies). `alembic_version` just got RLS enabled with no policy, since it's
Alembic's internal migration-tracking table and has no legitimate reason to be
queried via the API at all — enabling RLS with zero policies blocks all PostgREST
access to it outright.

**Why this didn't break the backend**: FastAPI connects via a direct Postgres
connection using a role with RLS-bypass privileges (Supabase's `postgres` role), so
none of this affects backend queries — RLS only constrains access through
PostgREST/the Supabase client libraries using the anon/publishable key, which is
exactly the gap being closed.

**How to apply**: any new table holding per-user data must get RLS enabled + an
owner policy in the same migration/provisioning pass that creates it — don't let this
gap reopen for the next table.

## 2026-08-18 — Statement upload: exact-file dedup via SHA-256; added a `queued` status

`upload_statement_file` (`backend/app/api/statements.py`) now hashes each upload
(SHA-256) and rejects an exact repeat for the same user with `409` before any Storage/
DB write — cheap (reuses bytes already read into memory), prevents wasted storage from
re-uploading the identical file. Deliberately no fuzzy or content-level dedup, just
exact-file matching.

`Statement.status` also gained a `queued` value, inserted between `uploaded` and
`processing`. Before this, a failed Celery enqueue left `status="uploaded"`
permanently and indistinguishably from "just uploaded, about to be queued." Now
`queued` means the enqueue itself succeeded, so `uploaded` unambiguously means "stored,
but the background job was never successfully queued" (no automatic retry exists yet).

## 2026-08-17 — Statement upload: scoped to upload/list/delete only, private bucket (unlike avatars' public one)

`POST/GET/DELETE /api/statements` (`backend/app/api/statements.py`) store uploaded
bank/credit-card statements (PDF or CSV, 20MB max) in a new `statements` table
(`backend/app/models/statement.py`, migration `684dfcb36717`) and a new private
Supabase Storage bucket (`statements`, `public=false`), following the same
caller's-own-JWT + folder-scoped-RLS pattern as the `avatars` bucket
(`statements_owner_all` policy, `for all` rather than avatars' insert-only policy,
since statements also need delete). `upload_statement`/`delete_statement` were added to
the existing `backend/app/services/storage.py` rather than a new module — one file for
all Supabase Storage interactions was simpler than splitting per bucket at this size.
Parsing the uploaded file into transactions was deliberately **not** built in this
pass — `Statement.status` defaults to `"uploaded"` and exists specifically so a future
parsing pipeline (likely the still-unused Celery `worker/`) has somewhere to record
progress without a schema change.

**Why**: (1) Avatars are meant to be publicly displayable; bank statements are
sensitive financial documents, so the bucket is private and no public URL is ever
generated or stored — only the internal `storage_path`, which `StatementRead` does not
expose. (2) Scoping to upload/list/delete (no parsing) was a deliberate choice made
with the user up front, to keep this session's change small and defer the bigger
architectural decision (sync parse in FastAPI vs. async via the Celery worker, and what
`shared/` types that would need) to when it's actually needed.

**How to apply**: when parsing is built, add a `parsed_at`/error columns or a separate
`transactions` table rather than overloading `status` with parse-result data, and
revisit whether `worker/` should get its first real task then.

## 2026-08-15 — Profile image upload: backend-proxied to Supabase Storage, bucket/RLS created via direct SQL

`POST /api/profile/image` takes a multipart upload, validates it in
`backend/app/services/storage.py` (JPEG/PNG/WebP only, 5MB max), and forwards it to
Supabase Storage's REST API using the _caller's own JWT_ (added `token` to
`CurrentUser` in `backend/app/core/security.py` to make this possible) — not a
service-role key. The `avatars` bucket and its RLS policy
(`avatars_owner_write`, scoped to `(storage.foldername(name))[1] = auth.uid()::text`)
were created by running raw SQL against `storage.buckets`/`storage.objects` over the
same Postgres connection Alembic uses, not through the Supabase dashboard.

**Why**: (1) Proxying through FastAPI instead of uploading straight from the browser to
Supabase Storage keeps "all business logic through FastAPI" intact (see the Server
Actions/FastAPI split decision below) and lets us enforce file type/size server-side
before it ever reaches Storage. (2) Using the user's own JWT rather than a service-role
key means the backend never needs a new admin secret — Storage RLS does the same
per-user authorization Postgres RLS would. (3) `storage.buckets`/`storage.objects` are
just Postgres tables, and this project already has a working superuser-ish connection
to them (the Alembic session-pooler URL) — creating the bucket that way was faster than
setting up dashboard/Management-API access, and is reversible (`delete from
storage.buckets where id = 'avatars'` + `drop policy`). This is a one-time
infra-provisioning step, not part of the Alembic-tracked `public` schema history —
Supabase owns the `storage` schema, so it's deliberately not folded into a migration.

**How to apply**: any future bucket needs the same two things — a `storage.buckets` row
and an owner-scoped RLS policy on `storage.objects` — done directly via SQL against the
project's Postgres connection, then referenced from a backend service module the same
way `storage.py` does. Don't introduce a Supabase service-role key for this unless a
feature genuinely needs cross-user access Storage RLS can't express.

## 2026-08-15 — Renamed `profiles` table to `users`; kept `/api/profile` route and schema names as-is

Migration `f63aac5142d7` renames `public.profiles` to `public.users` and adds
`created_at`, `updated_at` (both `server_default=now()`, `updated_at` also has
`onupdate=func.now()` so ORM-driven updates bump it), and `profile_image`
(nullable `VARCHAR(500)`, no upload endpoint yet — just a column for a future image
URL). The SQLAlchemy model moved from `app/models/profile.py` (`Profile`) to
`app/models/user.py` (`User`) to match the table it maps to.

The API route (`/api/profile`), Pydantic schema names (`ProfileRead`/`ProfileUpdate`,
`app/schemas/profile.py`), and router file (`app/api/profile.py`) were deliberately
**not** renamed.

**Why**: "profile" is the settings-page feature/contract the frontend already depends
on; "users" is what the underlying table should be called now that it's gaining
account-level fields (timestamps, avatar) beyond pure profile data. Renaming the route
too would touch the frontend (`frontend/src/constants/endpoints/settings.endpoints.ts`)
for no functional gain and wasn't part of the request.

**How to apply**: if this table grows further into a general "account" concept, revisit
whether `/api/profile` should become `/api/account` or `/api/user` — but don't rename
routes speculatively; only when a concrete new feature forces the question.

## 2026-08-11 — API architecture split: Server Actions for auth only, FastAPI for everything else

Next.js Server Actions (`frontend/src/app/**/actions.ts`) are scoped to Supabase auth
flows only (login, signup, logout, password reset, email confirm). Every other piece of
business logic — profile, and anything that follows — lives in FastAPI (`backend/`) and
is called from the frontend through the shared API service layer
(`services/app.service.ts` + `hooks/use-api-request.ts`).

**Why**: keeps a single source of truth for business logic and data access (FastAPI +
SQLAlchemy/Alembic against Supabase Postgres), instead of splitting it across two
runtimes. Auth stays in Server Actions because Supabase's SSR auth helpers are built
around Next.js's cookie/session handling.

**How to apply**: when adding a new feature, default to a FastAPI endpoint, not a new
Server Action, unless it's literally an auth operation.

## 2026-08-11 — Migrated `profiles` table to Supabase Postgres via SQLAlchemy + Alembic

Introduced SQLAlchemy models and Alembic migrations (`backend/app/models/`,
`backend/app/core/db.py`) instead of hand-written SQL or relying on Supabase's
auto-generated REST API for the `profiles` table.

**Why**: gives FastAPI direct, typed, migration-tracked control over schema evolution as
more tables get added, rather than depending on Supabase's PostgREST layer for
everything.

**How to apply**: new tables follow the same pattern — SQLAlchemy model + Alembic
migration + Pydantic schema in `backend/app/schemas/`.
