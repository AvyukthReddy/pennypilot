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

## Statement ingestion + analysis (upload → Document, Phase 1+2 — no parser yet)

Earlier parsing-pipeline attempts (`worker/worker/parsing/`) were deleted entirely —
never committed, so no history to preserve. See `docs/DECISIONS.md`'s "Statement
parsing scoped down to Phase 1" entry. This is intentionally Phase 1+2 only: get a
clean, well-described `Document` in front of a future parser, nothing more.

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
   each), and `images` (bounding boxes only). An unreadable/corrupt PDF ⇒
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

## Viewing extracted text blocks (statements page → document analysis)

1. `components/statements-list.tsx` shows a "Text blocks" link per statement row when
   `status === "ingested"` and `content_type === "application/pdf"`, linking to
   `/statements/analysis?statement_id={id}&filename={filename}`.
2. `frontend/src/app/statements/analysis/page.tsx` (server component, same auth-gate
   pattern as `/transactions`) renders `components/statement-pages-view.tsx`, which
   GETs `GET /api/statements/{id}/pages` (`backend/app/api/statements.py`, same
   ownership check as `/view`) via `statementsEndpoints.pages`.
3. The route returns `{ statement_id, pages }` straight from `Statement.pages`
   (`[]` if analysis hasn't finished/isn't a PDF) — validated against
   `StatementPagesRead`/`PageRead`/`TextBlockRead` (`backend/app/schemas/
   statement.py`). Not folded into `StatementRead` (used by the statements list)
   since a multi-page statement's full text-block list is much larger than everything
   else in that response.
4. Each page renders as a collapsible `<details>` (first page open, rest collapsed)
   with a table of `text_blocks` — `x`/`y`/`width`/`height`/`text`.

## Not yet wired

- **Actual parsing.** `worker/worker/tasks.py` has a `# TODO(phase 3): hand
  `document` to a real parser here.` marker at the exact seam. The `transactions`
  table/model/API (`GET /api/transactions`) and frontend Transactions page all exist
  and work — they just have nothing to display until a parser populates them.
- Transaction categorization (AI/merchant-based) and a full transaction-editing UI —
  depend on parsing existing first.
