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
- **Statement ingestion (Phase 1 — no parsing)**: after upload, a Celery task
  (`worker.parse_statement`) downloads the stored file unmodified, counts PDF pages
  (`worker/worker/pdf_info.py`, via `pypdf`), and builds a `Document`
  (`worker/worker/document.py` — bytes + `file_hash`/`size_bytes`/`page_count`/
  `parser_version`) — the explicit handoff object a future parser will consume.
  `Statement.page_count`/`parser_version` get persisted, `status` becomes
  `"ingested"`. No parser exists yet — earlier parsing-pipeline attempts were deleted
  entirely (never committed, so no history to preserve). See
  [DECISIONS.md](DECISIONS.md)'s "Statement parsing scoped down to Phase 1" entry, and
  `worker/worker/tasks.py`'s `# TODO(phase 2): hand document to a real parser here.`
  marker for exactly where the next parser plugs in.
- **Worker**: `worker/` (Celery) has one task (`worker.parse_statement`,
  `worker/worker/tasks.py`, ingestion only) with its own DB access layer
  (`worker/worker/config.py`, `db.py`, `models.py` — hand-mirrored, non-authoritative
  mappings; Alembic in `backend/` remains the sole schema authority). Dependencies are
  back to minimal: `celery[redis]`, `sqlalchemy`, `psycopg`, `httpx`, `pypdf`,
  `python-dotenv` — `pdfplumber`, `pydantic`, and the `shared/` path dependency were
  all removed since nothing uses them anymore.
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

- Nothing currently in flight. Last completed unit of work: scrapped the parsing
  pipeline entirely and rebuilt Phase 1 (document ingestion only — page count, file
  hash, size, parser version; no transaction extraction). Backend (31 tests) and
  worker (4 tests, down from 84 — the deleted tests were all for the deleted parsing
  code) pass; frontend `tsc --noEmit`/`eslint` clean.
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
- **No parser exists.** Every ingested statement lands at `status="ingested"` with an
  empty `transactions` table behind it — this is the current, intended state of Phase
  1, not a bug. The Transactions page/API work correctly, they just have nothing to
  show until Phase 2 (a real parser) exists.
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

- Phase 2: build a real parser that consumes the `Document` object
  (`worker/worker/document.py`) and produces `transactions` rows — the seam is marked
  with a `# TODO(phase 2)` comment in `worker/worker/tasks.py`. Not yet scoped/agreed
  how (deterministic vs. LLM-assisted, bank-specific vs. generic) — discuss with the
  user before starting.
- Run the Docker build once Docker Desktop is available (see "In progress" above).
