# Decisions

Append-only log of meaningful decisions and the reasoning behind them. Code shows what
changed; this shows why. New entries go at the top. Don't edit or delete past entries
when a decision is later reversed — add a new entry that supersedes it and link back.

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
Supabase Storage's REST API using the *caller's own JWT* (added `token` to
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
