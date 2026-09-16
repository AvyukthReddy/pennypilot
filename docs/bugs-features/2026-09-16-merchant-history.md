# Merchant history (per-user + global-consensus category suggestion)

**Type**: feature
**Status**: done
**Started**: 2026-09-16

## What & why

User asked ("Step 2: Merchant history") for the app to "get intelligent": once a user
categorizes a transaction from a merchant (e.g. Starbucks -> Food/Coffee), later
transactions from that same merchant should suggest that category automatically, at
high confidence, without AI. Must be user-specific (User A's Starbucks mapping must not
leak into User B's suggestions), with a "global merchant knowledge" fallback computed
from what other users picked, and a user's own choice always winning over the global
signal.

No transaction-level category assignment existed anywhere in the app before this
(confirmed via grep: zero hits for "category"/"merchant" in `transactions.py`,
`transaction.py`, or the worker). Scoped up front via three questions:

1. **Also build real transaction-category assignment** (a `transactions.category_id`
   column and a PATCH endpoint), not just the learning engine in isolation, since
   nothing else in the app could trigger "a user categorized a transaction" yet.
2. **"Global merchant knowledge" is computed dynamically**, aggregating every user's
   preference rows by category name, rather than stored as a static column. This
   resolves the exact tension Step 1 (merchant normalization) deliberately left open:
   `Merchant.default_category_id`/`default_subcategory_id` can't cleanly point at one
   specific user's per-user category row, since categories have no global/shared
   table. Those two columns stay untouched and unused.
3. **Numeric confidence**: 100 for a user's own history, a computed percentage for
   global consensus.

Full rationale in `docs/DECISIONS.md`'s 2026-09-16 "Merchant history" entry.

## Tried

- Considered whether `Merchant.default_category_id`/`default_subcategory_id` (added
  in Step 1) could be repurposed as the global-knowledge storage. Rejected: those are
  single FKs to one specific `categories.id` row, but categories are per-user, so a
  global merchant can never point at "the" category the way it points at "the" name.
  Went with dynamic aggregation over `MerchantCategoryPreference` rows instead, and
  left the Step 1 columns exactly as they were.
- First draft of the test-file `_eval_clause` helper (copied from
  `test_merchant_normalization.py`'s simpler version) didn't handle `IS NULL`
  comparisons. The top-level-category lookup in `_find_or_create_category`
  (`Category.parent_id == None`) produces a SQLAlchemy `Null` clause element that has
  no `.value` attribute, unlike a normal bound parameter. Caught immediately by
  `test_suggest_category_reuses_existing_category_instead_of_duplicating` failing with
  an `AttributeError`. Fixed by using `test_categories.py`'s fuller `_eval_clause`
  (checks `isinstance(right, sa.sql.elements.Null)` first), since this feature
  actually needs top-level lookups, unlike Step 1's normalization tests.
- Considered matching cross-user categories by name alone. Rejected: a top-level
  category and a differently-scoped subcategory can share a name (e.g. top-level
  "Food" versus someone's "Food" nested under "Restaurants"), which would incorrectly
  merge two distinct real-world categories into one vote bucket. Used
  `(name, parent name)` as the matching/grouping key instead, verified by a dedicated
  test (`test_suggest_category_distinguishes_top_level_from_subcategory_same_name`).

## What worked

- `backend/app/models/transaction.py`: added `merchant_id`/`category_id` nullable
  FKs.
- `backend/app/models/merchant_category_preference.py` (new):
  `MerchantCategoryPreference`, unique on `(user_id, merchant_id)`.
- Migration `d0c1c7b5b6d3` (chained after `d26cc8a6715d`): adds the two transaction
  columns plus the new table. First migration in the repo to add FK columns to an
  existing table rather than only create new tables, so it needed named constraints
  via `op.create_foreign_key`.
- `backend/app/services/merchant_category_learning.py` (new): `suggest_category`,
  `record_preference`, `_find_or_create_category`.
- `backend/app/schemas/transaction.py`: extended `TransactionRead`, added
  `CategorySuggestionRead`, `TransactionCategoryAssign`.
- `backend/app/api/transactions.py`: `_get_owned_transaction`, `_ensure_merchant`,
  `GET /api/transactions/{id}/category-suggestion`,
  `PATCH /api/transactions/{id}/category`.
- RLS enabled on `merchant_category_preferences` with an owner policy, via a one-off
  script (`scratch_enable_merchant_category_preferences_rls.py`, run once against the
  dev DB then deleted, matching the established convention).

## Verification

- `backend`: `pytest -q` -> 151 passed (133 pre-existing + 7 in
  `test_merchant_category_learning.py` + 11 in `test_transactions_category.py`).
  Covers the literal scenario from
  the request end to end: User A assigns Starbucks to Food/Coffee, a second Starbucks
  transaction for User A is suggested the same category at 100% confidence; once
  several users have categorized Starbucks, a new user gets a correctly computed
  `global_consensus` percentage resolved into their own category tree; that user then
  explicitly overrides to a different category, and their next suggestion flips to
  100% `user_history`, proving the override beats consensus; re-assigning updates
  rather than duplicates a preference row; auth and ownership checks on both new
  endpoints. `ruff check` clean on all new/changed files.
- `alembic upgrade head` / `alembic current` confirmed the migration applied cleanly
  against the dev Supabase DB.
- RLS confirmed via direct query: `pg_class.relrowsecurity` is true and
  `pg_policies` lists `merchant_category_preferences_owner_all` for the new table.
- Confirmed both new routes appear in the app's OpenAPI schema.
- **Not done / explicitly out of scope**: no frontend surface exists for this
  (backend-only pass), so there's nothing to click through in a browser. Statement
  ingestion still doesn't call `resolve_merchant`, and a genuinely learned/AI layer
  for merchants nobody has ever categorized is still unbuilt, see
  `docs/HANDOVER.md`'s "Next up" for the planned follow-ups.

A frontend category picker/suggestion UI, wiring `resolve_merchant` into statement
ingestion, and an AI fallback for merchants with zero preference history anywhere are
all separate, unbuilt follow-ups. Start a new file in this directory for any of them
rather than reopening this one.
