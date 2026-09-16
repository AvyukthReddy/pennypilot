# Merchant normalization (data model + normalization function only)

**Type**: feature
**Status**: done
**Started**: 2026-09-16

## What & why

User asked ("Step 1: Normalize the merchant") for a normalization layer that turns
ugly bank transaction description strings (e.g. `STARBUCKS #18273 AUSTIN TX`,
`SQ *STARBUCKS`, `AMZN MKTP US*2X82`) into canonical merchant names (`Starbucks`,
`Amazon`), backed by two new tables: `merchants` (id, name, default_category_id,
default_subcategory_id) and `merchant_aliases` (id, merchant_id, alias). No merchant
concept existed anywhere before this: `Transaction.description` holds the raw string
verbatim with zero cleanup, confirmed via a full-repo grep for "merchant" turning up
only forward-looking mentions in docs.

Scoped up front via three questions, since "normalize the merchant" bundled several
separable decisions:

1. **Table scope**: global/shared tables (no `user_id`), not per-user like
   `categories`. One canonical "Starbucks" row reused by every user.
2. **`default_category_id`/`default_subcategory_id`**: add as nullable FKs to
   `categories.id`, left unused/NULL this pass. Resolving what they mean for a
   global merchant pointing at a per-user category row is deferred.
3. **Unknown merchants**: auto-create a new `Merchant`/`MerchantAlias` row
   (self-learning), rather than only matching a fixed seeded set.

Full rationale in `docs/DECISIONS.md`'s 2026-09-16 entry.

## Tried

- Considered whether `merchants` should be per-user like `categories`. Rejected:
  unlike a category (a personal organizational label), a merchant like "Starbucks" is
  the same real-world entity for every user, so duplicating it per user would mean
  re-learning the same aliases from scratch for each account.
- First version of the trailing "CITY ST" regex (`_TRAILING_CITY_STATE_RE`) allowed an
  unbounded number of preceding words before the state code
  (`\s+[A-Z]+(?:\s+[A-Z]+)*\s+STATE$`). Caught by the test suite: for
  `"JOES PIZZA #4521 CHICAGO IL"`, the regex engine's leftmost-match search found its
  first successful match starting right after "JOES" and greedily consumed
  "PIZZA CHICAGO" as the "city", collapsing the merchant name to just `"Joes"` instead
  of `"Joes Pizza"`. Fixed by bounding the city portion to exactly one word
  (`\s+[A-Z]+\s+STATE$`). This means two-word cities (e.g. "SAN FRANCISCO CA") won't
  be fully stripped, but under-stripping is far safer than corrupting a real merchant
  name, and none of the request's example strings use a two-word city.
- Considered exposing `created_at` on `MerchantRead` (mirroring the model). Removed it:
  it relies on Postgres's `server_default=func.now()`, which never fires against the
  test suite's `FakeSession` (same reason `CategoryRead` omits `created_at` too),
  caught immediately by a Pydantic validation error in the API test.

## What worked

- `backend/app/models/merchant.py` (`Merchant`, `MerchantAlias`; migration
  `d26cc8a6715d`, chained after `25d591fb73a0`) · registered in
  `backend/alembic/env.py`'s autogenerate imports.
- `backend/app/services/default_merchant_aliases.py` (`DEFAULT_MERCHANT_ALIASES`
  prefix dictionary, mirrors `default_categories.py`'s shape).
- `backend/app/services/merchant_normalization.py`
  (`normalize_merchant_key`/`resolve_merchant`), the four-tier resolution described
  in `docs/DECISIONS.md`.
- `backend/app/schemas/merchant.py` (`MerchantRead`, `MerchantNormalizeRequest`) ·
  `backend/app/api/merchants.py` (`POST /api/merchants/normalize`, manual
  verification only) · registered in `backend/app/main.py`.
- Migration `d26cc8a6715d` applied to the dev Supabase DB (`alembic upgrade head`,
  confirmed via `alembic current`). No RLS provisioning needed: these are global
  tables, not per-user (see `docs/DECISIONS.md`).

## Verification

- `backend`: `pytest -q` -> 133 passed (124 pre-existing + 6 in
  `test_merchant_normalization.py` + 3 in `test_merchants_api.py`). Covers: all four
  Starbucks description variants converging on one `Merchant` row via tier-1 regex
  alone; all four Amazon variants converging on one `Merchant` row via the
  seed-dictionary tier; repeat calls with the same raw string not duplicating rows;
  an unseeded description auto-creating a new merchant; the API endpoint requiring
  auth and resolving/reusing merchants across requests. `ruff check` clean on all
  new/changed files.
- Manual: confirmed `POST /api/merchants/normalize` is registered (present in the
  app's OpenAPI schema) after adding the router to `main.py`.
- **Not done / explicitly out of scope**: no frontend surface exists for this
  (backend-only pass), so there's nothing to click through in a browser. Statement
  ingestion, `transactions.merchant_id`, and category auto-assignment are all
  unbuilt, see `docs/HANDOVER.md`'s "Next up" for the planned follow-ups.

Wiring `resolve_merchant` into ingestion/read paths, adding
`transactions.merchant_id`, and resolving the default-category tension for
auto-categorization are all separate, unbuilt follow-ups. Start a new file in this
directory for any of them rather than reopening this one.
