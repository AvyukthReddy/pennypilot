# Category system (taxonomy only)

**Type**: feature
**Status**: done
**Started**: 2026-08-28

## What & why

User asked to build a category system: default categories, subcategories, and
user-created categories. No category concept existed anywhere before this (only
AI-prompt boilerplate text and a hardcoded landing-page marketing mockup) — the
`Transaction` model has no category column, and `docs/HANDOVER.md` already flagged
"Transaction categorization" as a future feature.

Scoped with the user up front via three questions, since "build categories" bundled
several separable decisions:

1. **Scope**: data model + management UI only, no transaction wiring this pass. A
   category filter/badge on individual transactions, and letting users assign a
   category to a transaction, are explicitly deferred to a follow-up.
2. **AI auto-categorization**: deferred — this pass is the manual taxonomy only.
3. **Nesting**: two fixed levels (category + subcategory), not arbitrary-depth.

Full rationale for the schema/UI choices is in docs/DECISIONS.md's 2026-08-28 entry.

## Tried

- Considered mirroring the institution/account-type-tags override pattern on
  `Statement` (`backend/app/services/statement_fields.py`) since it was the most
  recent, most analogous prior feature. Rejected: that pattern is for unbounded
  free-text per-statement tags with no shared identity across rows. Categories need
  real, reusable, renameable rows (a `categories` table), not an override column.
- First pass at `create_category`/`_seed_defaults` relied on `Category`'s
  `mapped_column(..., default=uuid.uuid4)` to populate `id` at flush time. Caught by
  the test suite (not manually): `FakeSession.commit()`/`.refresh()` are no-ops (same
  convention as `test_statements.py`), so `category.id` stayed `None` through a whole
  request, failing Pydantic validation on the response. Fixed by generating
  `id=uuid.uuid4()` explicitly in the constructor, matching how
  `upload_statement_file` in `app/api/statements.py` already does this for the same
  reason.
- Initially returned `204 No Content` from `DELETE /api/categories/{id}`. Same trap
  documented in `2026-08-17-statement-upload.md`: the frontend's shared
  `getResponseAsync` always calls `response.json()` on success, which throws on an
  empty body. Changed to `200` with `{"id": ...}`, matching
  `DELETE /api/statements/{id}`'s convention.
- Live browser click-through was attempted but not completed: the Claude Chrome
  extension was not connected in this session (`tabs_context_mcp` returned "Browser
  extension is not connected"). Backend (`uvicorn`, port 8000) and frontend (an
  already-running `next dev` on port 3000) were both confirmed up and responding
  (`/api/categories` returns 401 without auth, confirming the router is live), but
  the actual create/rename/reorder/delete flow through the UI has not been clicked
  through by an agent or the user yet.

## What worked

- **Backend**: `backend/app/models/category.py` (`Category`, table `categories`,
  migration `25d591fb73a0`, chained after `07f7b7d96535`) ·
  `backend/app/services/default_categories.py` (`DEFAULT_CATEGORIES` constant) ·
  `backend/app/schemas/category.py` (`CategoryCreate`/`CategoryUpdate`/`CategoryRead`/
  `CategoryReorderRequest`) · `backend/app/api/categories.py` (`GET/POST
  /api/categories`, `PATCH /api/categories/reorder`, `PATCH/DELETE
  /api/categories/{id}`, `_get_owned_category` ownership helper, `_seed_defaults`,
  `_to_tree`) · registered in `backend/app/main.py` · model registered in
  `backend/alembic/env.py`'s autogenerate imports.
- **Frontend**: `frontend/src/constants/endpoints/categories.endpoints.ts` ·
  `frontend/src/components/settings/categories-manager.tsx` (nested list, inline
  rename, delete, add category/subcategory, up/down reorder) ·
  `frontend/src/components/shared/skeleton.tsx` (`CategoriesSkeleton` added) · new
  "Categories" section added to `frontend/src/app/settings/page.tsx`, between
  Profile and Password.
- Migration `25d591fb73a0` applied to the dev Supabase DB (`alembic upgrade head`,
  confirmed via `alembic current`).
- RLS enabled on `categories` with a `categories_owner_all` owner policy, via a
  one-off script (`backend/scratch_enable_categories_rls.py`, run once then
  deleted) -- the standing rule from docs/DECISIONS.md's 2026-08-18 entry ("any new
  table holding per-user data must get RLS + an owner policy in the same pass").
  Confirmed via `pg_class.relrowsecurity`/`pg_policies` and a full backend test run.

## Verification

- `backend`: `pytest -q` → 124 passed (110 pre-existing + 14 new in
  `tests/test_categories.py`). Covers: auth-required, default seeding on first fetch
  (and not re-seeding once categories exist), top-level and subcategory creation,
  rejecting a subcategory-of-a-subcategory, rejecting duplicate names
  (case-insensitive) at the same level, rejecting a parent owned by another user,
  rename (including duplicate-name rejection and ownership isolation), delete,
  reorder (including rejecting a set of ids that doesn't match the current siblings).
  `ruff check` clean on all new/changed backend files.
- `frontend`: `npx tsc --noEmit` clean; `npx eslint` clean on all new/changed files
  (one `react-hooks/set-state-in-effect` finding along the way, fixed by calling
  `.then()` directly on the request in the initial-load `useEffect` instead of
  delegating through a named `refresh()` helper, matching
  `account-type-tags-editor.tsx`'s existing pattern).
- **Not yet done**: live browser click-through (see "Tried" above). Next session
  (or the user) should open Settings, confirm the Categories section seeds the
  default taxonomy on first load, and exercise create/rename/reorder/delete for both
  top-level categories and subcategories before considering this fully verified.

Transaction-level category assignment/filtering and AI/merchant-based
auto-categorization are still outstanding — start a new file in this directory for
either of those rather than reopening this one.
