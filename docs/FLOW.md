# Flow

How execution actually travels between files, functions, and modules for each major
path. Update the relevant section whenever you touch a file on that path — bugs live in
the gaps between files, so this only earns its keep if it stays accurate.

## Auth (login / signup / logout / password reset)

1. Browser hits a page under `frontend/src/app/{login,signup,forgot-password,reset-password}/`.
2. Form submits to that route's Server Action in the sibling `actions.ts`
   (e.g. `frontend/src/app/login/actions.ts`).
3. Action calls the Supabase client from `frontend/src/lib/supabase/server.ts`.
4. `frontend/src/proxy.ts` + `frontend/src/lib/supabase/middleware.ts` run on every
   request to refresh/validate the Supabase session cookie and gate protected routes.
5. Email-based flows (confirm, callback) land on `frontend/src/app/auth/callback/route.ts`
   or `frontend/src/app/auth/confirm/route.ts`, which exchange the code/token with
   Supabase and redirect into the app.

## Profile read/write (settings page)

1. `frontend/src/app/settings/page.tsx` renders `components/profile-form.tsx`.
2. The form calls `hooks/use-api-request.ts`, which goes through
   `services/app.service.ts` to hit the FastAPI backend at the URL/paths defined in
   `constants/endpoints/settings.endpoints.ts`.
3. Request carries the Supabase JWT (from the client-side Supabase session); FastAPI
   verifies it in `backend/app/core/security.py` before the route handler runs.
4. `backend/app/api/profile.py` (`GET/PUT /api/profile`) reads/writes through the
   `User` SQLAlchemy model in `backend/app/models/user.py` (maps to the `users` table)
   (schema validated by `backend/app/schemas/profile.py`) against Supabase Postgres via
   `backend/app/core/db.py`.
5. CORS is configured in `backend/app/main.py` to allow the frontend origin.

## Profile image upload (settings page)

1. `components/profile-form.tsx`'s avatar button opens a hidden file input; on change,
   files over 5MB are downscaled (max 1024px long edge) and re-encoded as JPEG in
   `lib/compress-image.ts` (canvas-based, quality stepped down until it fits) before
   upload — files already under 5MB are sent as-is. The result POSTs as `FormData` to
   `settingsEndpoints.profileImage()` via `use-api-request.ts` (which already skips the
   JSON `Content-Type` header for `FormData` bodies, so the browser sets the multipart
   boundary).
2. `backend/app/api/profile.py`'s `upload_profile_image` reads the file, validates it
   (JPEG/PNG/WebP, 5MB max) in `backend/app/services/storage.py`, then uploads it to the
   Supabase Storage `avatars` bucket using the same user JWT that authenticated the
   request — Storage RLS (policy `avatars_owner_write`) restricts writes to the caller's
   own `{user_id}/` folder.
3. The returned public URL (cache-busted with `?v=<timestamp>`) is written to
   `users.profile_image` and the updated `ProfileRead` is returned, so the frontend
   updates the avatar immediately.

## Statement upload (statements page)

1. `frontend/src/app/statements/page.tsx` renders `components/statements-list.tsx`,
   reachable via the "Statements" link in `components/navbar.tsx`.
2. On mount, the component GETs `settingsEndpoints`-style
   `constants/endpoints/statements.endpoints.ts` → `/api/statements` through
   `hooks/use-api-request.ts` to list the signed-in user's statements.
3. Choosing a file (PDF/CSV, ≤20MB, checked client-side first) POSTs it as `FormData`
   to the same `/api/statements` path.
4. `backend/app/api/statements.py`'s `upload_statement_file` reads the file and calls
   `upload_statement` in `backend/app/services/storage.py`, which validates
   type/size server-side and uploads to the private Supabase Storage `statements`
   bucket under `{user_id}/{statement_id}.{ext}`, using the caller's own JWT — Storage
   RLS (`statements_owner_all`) restricts access to the caller's own folder.
5. A `Statement` row (`backend/app/models/statement.py`) is written via SQLAlchemy
   before file_hash-based dedup and the parse-task enqueue (see "Statement parsing"
   below); the `StatementRead` schema (no `storage_path`/`file_hash` fields) is
   returned so the frontend can show the new entry immediately.
6. Clicking "View" GETs `/api/statements/{id}/view`, which checks ownership (shared
   `_get_owned_statement` helper) and calls `get_statement_view_url` in `storage.py` to
   mint a short-lived (120s) Supabase Storage signed URL — the bucket is private, so
   there's no standing public URL to hand back. The frontend opens a blank tab
   synchronously on click (to dodge popup blockers), then redirects it to the signed
   URL once the response arrives.
7. Removing a statement DELETEs `/api/statements/{id}`, which checks the row belongs to
   the caller (same `_get_owned_statement` helper), deletes the Storage object via
   `delete_statement`, then deletes the row.
8. The statements list polls `GET /api/statements` every ~4s
   (`components/statements-list.tsx`) while any statement is `uploaded`/`queued`/
   `processing`, and renders `parse_error` under the status line once parsing
   finishes (or fails/warns) — see "Statement parsing" below.

## Statement ingestion, analysis, understanding, region detection, schema discovery, transaction extraction, verification, and financial validation (upload → Document → transactions, Phase 1+2+3+4+5+6+7+8)

Earlier parsing-pipeline attempts (`worker/worker/parsing/`) were deleted entirely —
never committed, so no history to preserve. See `docs/DECISIONS.md`'s "Statement
parsing scoped down to Phase 1" entry. This covers ingestion, page/text extraction,
document-level classification, narrowing to transaction-table regions, discovering
each region's column layout, extracting and AI-verifying every transaction row, and
finally a deterministic (non-AI) arithmetic/sanity pass over the result.

1. In `upload_statement_file` (`backend/app/api/statements.py`), right after the
   `Statement` row is created: a SHA-256 `file_hash` of the uploaded bytes is checked
   against the caller's existing statements — a match short-circuits with `409` before
   any Storage/DB write. On a fresh file, a 600s Supabase signed URL is minted
   (`get_statement_view_url`) and `enqueue_parse_statement` (`backend/app/core/
celery_client.py`) publishes a `worker.parse_statement` task (by name only — the
   backend never imports worker code) onto the Redis broker (`settings.redis_url`).
   On success, `Statement.status` becomes `"queued"`; if enqueueing itself fails, the
   statement stays `"uploaded"` (a documented terminal state meaning "stored, not yet
   queued" — no auto-retry exists).
2. `worker/worker/tasks.py`'s `parse_statement(statement_id, signed_url)` picks up the
   task: loads its own `StatementRow` mapping (`worker/worker/models.py` — a
   hand-mirrored, non-authoritative copy of the backend's schema, see that file's
   top-of-file comment), sets `status="processing"`, then `httpx.get`s the file via the
   signed URL — a download failure surfaces only a fixed generic `parse_error`, never
   the exception text, since it could embed the URL/token. **Known gap**: httpx's own
   request logging still prints the full signed URL (including its token) at INFO
   level regardless — this app-level redaction doesn't suppress that. The downloaded
   bytes are never modified.
3. For PDFs, `worker/worker/pdf_analysis.py`'s `analyze_pdf` (via `pdfplumber`) opens
   the file and returns one `Page` per page (`worker/worker/document.py`): `width`/
   `height`, full `text`, line-grouped `text_blocks` (`text`/`x`/`y`/`width`/`height`
   each), `images` (bounding boxes only), and a rendered `image` (a PNG raster of the
   whole page, at `PAGE_IMAGE_RESOLUTION` — `None` if rendering fails for that page;
   kept in-memory only, never persisted — see step 8/10 and `docs/DECISIONS.md`'s
   2026-08-24 "Phase 6 follow-up" entry). An unreadable/corrupt PDF ⇒
   `status="failed"`. CSVs skip this — `pages` stays `[]`, page count is `None`.
   `is_scanned(pages)` then flags `needs_ocr` when a PDF's average
   characters-per-page falls below a small threshold — a scanned/image-only document
   with no real text layer. No OCR/vision runs yet; this is detection only.
4. A `Document` (`worker/worker/document.py`) is built: `statement_id`, `filename`,
   `content_type`, `data`, `file_hash`, `size_bytes`, `page_count`, `parser_version`
   (`INGESTION_VERSION` in `tasks.py`, bumped when ingestion/analysis logic changes),
   plus `pages` and `needs_ocr`. This is the explicit handoff object a future parser
   will consume — nothing reads it for parsing purposes yet.
5. `page_count`/`parser_version`/`needs_ocr` are persisted on the `Statement` row,
   along with `pages` itself (serialized via `dataclasses.asdict`, stored in a `JSONB`
   column — migration `b2e3d4f5a6c7`, see `docs/DECISIONS.md`'s 2026-08-19 "Persist
   `Statement.pages`" entry). `status="ingested"` (there is no `"parsed"`/
   `"unsupported"` anymore — nothing attempts to interpret file contents, so there's
   nothing to succeed or reject at that level). A scanned PDF still reaches
   `status="ingested"` — `needs_ocr=true` is a flag, not a failure.
6. Any unhandled exception past the download step rolls back, sets `status="failed"`
   with a truncated exception message, and re-raises so Celery still logs it.
7. When the statement is a PDF with real text (`not needs_ocr` and `pages` non-empty),
   `worker/worker/document_understanding.py`'s `DocumentUnderstandingService.analyze`
   feeds each page's `text` to an `AIProvider` (`worker/worker/ai_provider.py` — a
   thin wrapper over any OpenAI-compatible endpoint, configured via
   `AI_BASE_URL`/`MODEL_API_KEY`/`AI_MODEL`; defaults to Hugging Face's Inference
   Providers router serving Qwen2.5-VL-7B-Instruct) and validates the reply against
   the closed `DocumentAnalysis` Pydantic schema (`worker/worker/document_analysis.py`)
   — document type, institution, account type/last4, currency, statement period,
   beginning/ending balance (when a balance summary is visible), and page-ranged
   `sections`. Invalid JSON triggers one self-repair retry before
   giving up. This step is **best-effort**: any failure (missing `MODEL_API_KEY`,
   network error, model never returns valid JSON) is caught, logged, and leaves
   `Statement.document_analysis` as `null` —
   ingestion has already succeeded by this point, so classification failing doesn't
   flip `status` to `"failed"`. See `docs/DECISIONS.md`'s 2026-08-19 "Phase 3" entry.
   `document_analysis` is persisted as `JSONB` (migration `c3f4a5b6d7e8`) alongside
   `pages`/`needs_ocr`/`page_count` in the same `session.commit()`.
8. When `document_analysis` exists and has a `sections` entry with
   `type == "transactions"`, `worker/worker/transaction_region_detection.py`'s
   `TransactionRegionDetectionService.detect` narrows further: only the pages in
   that section are examined (`_candidate_pages`), and one user message per
   flagged page is sent within a single call — each page's `text_blocks` (with
   `x`/`y`/`width`/`height` this time, not just flat text — naming a bounding
   region needs layout) as a text part, plus that page's rendered image
   (`Page.image`, when available) as an `image_url` part, so the model can
   visually cross-check the region it picks. The reply is validated against
   the closed `TransactionRegionDetection` schema
   (`worker/worker/transaction_regions.py`) — one `[x0, y0, x1, y1]` region
   per page. Same `AIProvider`, same one-self-repair-retry, same
   best-effort/non-fatal handling as step 7 — a failure here leaves
   `Statement.transaction_regions` as `null` without touching `status`. Skipped
   entirely (no call made) when there's no `"transactions"` section to narrow
   (including the `needs_ocr`/no-`document_analysis` cases from step 7). Persisted
   as `JSONB` (migration `d4e5f6a7b8c9`) in the same `session.commit()`. See
   `docs/DECISIONS.md`'s 2026-08-19 "Phase 4" and 2026-08-24 "Phase 6
   follow-up" entries.
9. When `transaction_regions` is non-empty,
   `worker/worker/transaction_schema_discovery.py`'s
   `TransactionSchemaDiscoveryService.discover` answers "what does a
   transaction look like in this document?" — for each detected region,
   `_blocks_in_region` crops that page's `text_blocks` down to just the ones
   inside the region (center-point test), all cropped regions are batched into
   one prompt, and the reply is validated against the closed
   `TransactionSchemaDiscovery` schema (`worker/worker/transaction_schema.py`)
   — a `transaction_fields` mapping from `Transaction`'s fixed fields
   (`transaction_date`/`post_date`/`description`/`amount`/`currency`) onto
   this document's actual columns (`"column_N"`, positional labels the model
   assigns itself). `amount` is a list, since a table with separate
   Debit/Credit columns needs two source mappings, each tagged
   `semantics: "debit"`/`"credit"`. Same `AIProvider`, same one-self-repair
   -retry, same best-effort/non-fatal handling as steps 7–8 — a failure here
   leaves `Statement.transaction_schema` as `null` without touching `status`.
   Skipped entirely when there are no detected regions to examine. Persisted
   as `JSONB` (migration `e5f6a7b8c9d0`) in the same `session.commit()`. See
   `docs/DECISIONS.md`'s 2026-08-23 "Phase 5" entry.
10. When `transaction_schema` was discovered,
    `worker/worker/transaction_extraction.py`'s
    `TransactionExtractionService.extract` runs **once per detected region**
    (not once per document, unlike steps 7-9) — each call crops just that
    page's `text_blocks` down to its region (`worker/worker/_regions.py`'s
    `_blocks_in_region`) as a text part, plus (via that same module's
    `_image_for_region`) the region cropped out of `Page.image` as an
    `image_url` part when available, so the model can visually cross-check
    row values the text extraction might have gotten wrong (misaligned
    columns, merged cells). The call is also prompted with the Phase 5
    column mapping for the whole document, so the model knows which column
    means what without re-deriving it per page. The reply is validated
    against the closed `TransactionExtraction` schema
    (`worker/worker/extracted_transactions.py`) — a list of
    `transaction_date`/`post_date`/`description`/`amount`/`currency` rows,
    nothing else (no category, no prose). Same `AIProvider`, same
    one-self-repair-retry as steps 7-9, but best-effort **per region**: one
    page's extraction failing doesn't discard transactions already
    extracted from other pages. A row's `currency` falls back to
    `document_analysis.currency` when the model leaves it `null`. Every
    successfully extracted row becomes a `TransactionRow`
    (`worker/worker/models.py`) and all of them are `session.add_all`'d
    alongside the existing `session.commit()` — the first phase that writes
    new rows into the `transactions` table rather than only mutating the
    `Statement` row. Skipped entirely when there's no `transaction_schema`.
    See `docs/DECISIONS.md`'s 2026-08-24 "Phase 6" and "Phase 6 follow-up"
    entries.
11. Immediately after a region's extraction succeeds,
    `worker/worker/transaction_verification.py`'s
    `TransactionVerificationService.verify` checks that extraction against
    the same region content (`_regions.py`'s `_region_content` — the same
    text+image builder step 10 uses) plus the extracted JSON itself, for
    missing/duplicate transactions, wrong dates/amounts/signs, and
    split-or-merged multi-line rows. The reply is validated against the
    closed `TransactionVerification` schema
    (`worker/worker/verification_issues.py`). Same `AIProvider`, same
    one-self-repair-retry, but best-effort in a new way: if verification
    itself fails, the region's original extraction is kept as-is
    (uncorrected). If verification succeeds and comes back `valid=false`,
    `TransactionExtractionService.extract` is called again for that same
    region with `previous_attempt`/`verification_issues` set — the prior
    JSON answer plus the issues are appended to the prompt as correction
    feedback — and whatever that retry produces is what actually becomes
    `TransactionRow`s, whether or not it's still flagged (no
    re-verification loop; a retry failure falls back to the pre-retry
    extraction). Every region's *first* verification result is aggregated
    into `Statement.transaction_verification` (`JSONB`, migration
    `f6a7b8c9d0e1`) in the same `session.commit()` as everything else. See
    `docs/DECISIONS.md`'s 2026-08-24 "Phase 7" entry.
12. Once the region loop finishes, if any rows were extracted,
    `worker/worker/financial_validation.py`'s `validate_transactions`
    (a plain Python function — no AI call, no provider, nothing to mock)
    runs once over the *entire* final `extracted_rows` list: date sanity
    (`post_date` before `transaction_date`, implausible years, dates outside
    the statement period), amount sanity (zero, or more than 2 decimal
    places), duplicate `(transaction_date, description, amount)` tuples, and
    — only when `document_analysis` states both a beginning and ending
    balance — `beginning_balance + sum(all signed amounts)` compared to
    `ending_balance` within a $0.01 tolerance. Wrapped in its own
    try/except but otherwise unconditional (no `AIProvider`/config
    dependency to fail on). Purely diagnostic — never blocks persistence or
    triggers re-extraction, never touches `status`. Persisted as
    `Statement.financial_validation` (`JSONB`, migration `a7b8c9d0e1f2`) in
    the same `session.commit()`. See `docs/DECISIONS.md`'s 2026-08-24
    "Phase 8" entry.

## Viewing extracted text blocks, document classification, detected regions, discovered schema, verification, and financial validation (statements page → document analysis)

1. `components/statements-list.tsx` shows a "Text blocks" link per statement row when
   `status === "ingested"` and `content_type === "application/pdf"`, linking to
   `/statements/analysis?statement_id={id}&filename={filename}`.
2. `frontend/src/app/statements/analysis/page.tsx` (server component, same auth-gate
   pattern as `/transactions`) renders, top to bottom:
   `components/document-analysis-summary.tsx`, `components/
transaction-regions-view.tsx`, `components/transaction-schema-view.tsx`,
   `components/transaction-verification-view.tsx`,
   `components/financial-validation-view.tsx`, then
   `components/statement-pages-view.tsx`. The summary card GETs
   `GET /api/statements/{id}/analysis` (`backend/app/api/statements.py`, same
   ownership check as `/view`/`/pages`) via `statementsEndpoints.analysis`, showing
   `document_type`/institution/account/currency/period/beginning and ending
   balance plus a page-ranged section
   list — or "Not yet classified" when `document_analysis` is `null` (still
   processing, or skipped for a scanned PDF). The regions table GETs
   `GET /api/statements/{id}/transaction-regions` via
   `statementsEndpoints.transactionRegions`, showing a page/region row per detected
   region — or an explanatory empty state when `null`/empty. The schema table GETs
   `GET /api/statements/{id}/transaction-schema` via
   `statementsEndpoints.transactionSchema`, showing a target-field → source-column
   row per discovered field (multiple rows for a split-amount `debit`/`credit`
   table) — or an explanatory empty state when `null`. The verification table GETs
   `GET /api/statements/{id}/transaction-verification` via
   `statementsEndpoints.transactionVerification`, showing "all verified" when
   `valid` with no issues, a type/page/description row per flagged issue when not,
   or an explanatory empty state when verification hasn't run (`valid` is `null`).
   The financial validation section GETs
   `GET /api/statements/{id}/financial-validation` via
   `statementsEndpoints.financialValidation`, showing "all checks passed" when
   `valid` with no issues, a type/description issue table plus a
   beginning/net-change/expected-vs-actual-ending balance breakdown when a
   balance check was run, or an explanatory empty state when validation hasn't
   run. The text-blocks viewer at the bottom GETs `GET /api/statements/{id}/pages`
   via `statementsEndpoints.pages`.
3. The `/pages` route returns `{ statement_id, pages }` straight from
   `Statement.pages` (`[]` if analysis hasn't finished/isn't a PDF) — validated
   against `StatementPagesRead`/`PageRead`/`TextBlockRead`; `/transaction-regions`
   returns `{ statement_id, transaction_regions }` from
   `Statement.transaction_regions` (unwrapping the persisted
   `{"transaction_regions": [...]}` shape), validated against
   `StatementTransactionRegionsRead`/`TransactionRegionRead`; `/transaction-schema`
   returns `{ statement_id, transaction_fields }` from
   `Statement.transaction_schema` (unwrapping `{"transaction_fields": {...}}`),
   validated against `StatementTransactionSchemaRead`/`TransactionFieldsRead`/
   `FieldSourceRead`; `/transaction-verification` returns
   `{ statement_id, valid, issues }` from `Statement.transaction_verification`
   (unwrapping `{"valid": ..., "issues": [...]}`, `valid` is `null` and `issues`
   is `[]` when verification hasn't run), validated against
   `StatementTransactionVerificationRead`/`VerificationIssueRead`;
   `/financial-validation` returns `{ statement_id, valid, issues, balance_check }`
   from `Statement.financial_validation` (unwrapping `{"valid": ..., "issues":
   [...], "balance_check": ...}`, `valid` is `null`, `issues` is `[]`, and
   `balance_check` is `null` when validation hasn't run), validated against
   `StatementFinancialValidationRead`/`FinancialValidationIssueRead`/
   `BalanceCheckRead` (all in `backend/app/schemas/statement.py`). None of these
   are folded into `StatementRead` (used by the statements list) — each can be
   much larger than everything else in that response.
4. Each page in the text-blocks viewer renders as a collapsible `<details>` (first
   page open, rest collapsed) with a table of `text_blocks` —
   `x`/`y`/`width`/`height`/`text`.

## Not yet wired

- Transaction categorization (AI/merchant-based) and a full transaction-editing UI.
- No dedup/idempotency guard on statement reprocessing: re-running
  `worker.parse_statement` on an already-`"ingested"` statement inserts a
  second set of `transactions` rows rather than replacing the first — the
  JSONB columns (`pages`/`document_analysis`/etc.) already overwrite cleanly
  on reprocessing, `transactions` rows don't yet. See `docs/DECISIONS.md`'s
  2026-08-24 "Phase 6" entry.
- OCR/vision for scanned PDFs (`needs_ocr=true`) — still detection-only; document
  understanding is skipped for these, not just transaction parsing.
