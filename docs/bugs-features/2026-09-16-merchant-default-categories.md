# Seeded default category tier for merchant suggestions

**Type**: feature
**Status**: done
**Started**: 2026-09-16

## What & why

User asked ("User-specific categorization") for a curated baseline mapping
("globally, Amazon -> Shopping") that gives a brand-new merchant a reasonable
starting suggestion even before any user has categorized it, while still losing to
both a user's own choice and to real cross-user consensus once either exists.

The merchant-history feature shipped earlier this session already implemented
"user-specific wins over global," but its "global" tier was a computed cross-user
consensus that only exists once at least one other user has categorized a merchant.
There was no true starting-point default: for a merchant nobody had ever
categorized, `suggest_category()` returned `None`, not a curated guess. Confirmed
this gap directly with the user before planning (asked whether the request was for
this specific gap or just confirming the already-shipped behavior; they confirmed
the gap).

Full precedence after this change: user's own preference (confidence 100) over
cross-user consensus, if any exists (computed percentage) over a curated seed
default, if one exists for this merchant name (fixed confidence) over no
suggestion. Full rationale in `docs/DECISIONS.md`'s 2026-09-16 "Seeded default
category tier for merchant suggestions" entry.

## Tried

Nothing notable went wrong. The existing `_find_or_create_category` helper (built
for the cross-user consensus tier) was already generic enough to resolve a
`(category_name, parent_name)` pair for any user, so the new tier needed no new
category-resolution logic, only a lookup into a new seed dict and a new early-return
branch in `suggest_category`.

## What worked

- `backend/app/services/default_merchant_categories.py` (new):
  `DEFAULT_MERCHANT_CATEGORIES`, a hand-curated `dict[str, tuple[str, str | None]]`
  keyed by merchant name, mirroring `default_categories.py`'s and
  `default_merchant_aliases.py`'s established shape (plain Python constant, no DB
  table, no migration).
- `backend/app/services/merchant_category_learning.py`: added
  `SEEDED_DEFAULT_CONFIDENCE = 50`, `_seeded_suggestion`, and wired it in as the
  fallback both places `suggest_category` previously returned `None` early
  (no-other-users'-preferences and no-votes-after-filtering). `CategorySuggestion`'s
  `source` literal gained `"seeded_default"`.
- `backend/app/schemas/transaction.py`: `CategorySuggestionRead.source` gained the
  same literal.
- Tests: extended `test_merchant_category_learning.py` with the seeded-default
  return path, reuse-not-duplicate behavior, and two precedence-order checks
  (consensus beats seed, user history beats seed); extended
  `test_transactions_category.py` with one endpoint-level case using a real
  `resolve_merchant`-resolved "Amazon" merchant and zero preference rows anywhere.

## Verification

- `backend`: `pytest -q` -> 157 passed (151 pre-existing + 6 new: 5 in
  `test_merchant_category_learning.py`, 1 in `test_transactions_category.py`).
  Covers: seeded suggestion returned with the right category and confidence when
  nothing else exists; an existing matching category reused rather than duplicated;
  cross-user consensus outranks the seed once real data exists; a user's own
  history outranks the seed; an unseeded merchant name with no history still
  returns `None`, no regression. `ruff check` clean on all new/changed files.
- No migration and no RLS change needed: this tier reads a Python constant, not a
  new table, confirmed by `git status` showing no new alembic revision file.

No frontend surface, wiring `resolve_merchant` into statement ingestion, and an AI
fallback for merchants with zero preference history anywhere and no seed entry
remain separate, unbuilt follow-ups, same as noted in the merchant-history trace.
