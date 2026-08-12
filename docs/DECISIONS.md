# Decisions

Append-only log of meaningful decisions and the reasoning behind them. Code shows what
changed; this shows why. New entries go at the top. Don't edit or delete past entries
when a decision is later reversed — add a new entry that supersedes it and link back.

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
