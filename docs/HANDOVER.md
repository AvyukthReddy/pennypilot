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
- **Profile**: `profiles` table lives in Supabase Postgres, managed via SQLAlchemy +
  Alembic (`backend/app/models/profile.py`). `GET/PUT /api/profile` exposed with CORS.
  Frontend account settings page (`frontend/src/app/settings/`) reads/writes it through
  the shared API service layer (`frontend/src/services/app.service.ts`,
  `hooks/use-api-request.ts`).
- **Worker**: `worker/` scaffolded (Celery) but no tasks implemented yet beyond the
  placeholder in `worker/worker/tasks.py`.
- **Shared**: `shared/` is empty — intended for cross-service Pydantic models/enums once
  a feature needs backend and worker to agree on a type.

## In progress

- Nothing currently in flight. Last completed unit of work: account settings page
  (profile + password), see `git log -1`.

## Known broken / rough edges

- None tracked yet — file bug traces under `docs/bugs-features/` as they come up.

## What to avoid

- Don't put business logic in Next.js Server Actions — auth only. Everything else goes
  through FastAPI. (See [DECISIONS.md](DECISIONS.md) for why.)
- Don't assume Next.js APIs match training data — this repo is on Next.js 16 with
  breaking changes; check `frontend/node_modules/next/dist/docs/` first.

## Next up

- Not yet decided — check with the user before picking the next feature.
