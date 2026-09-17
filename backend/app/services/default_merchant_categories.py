"""Hand-curated baseline category mappings used by merchant_category_learning.py's
suggest_category as a last-resort tier, when a merchant has no cross-user consensus
yet (nobody on this instance has categorized it) and the asking user has no
preference of their own. Keyed by Merchant.name (the canonical name
resolve_merchant already produces), valued by (category_name,
subcategory_name_or_None). A user's own choice, and any real cross-user consensus,
both outrank this: it exists only to give a brand-new merchant a reasonable
starting suggestion instead of none at all.
"""

DEFAULT_MERCHANT_CATEGORIES: dict[str, tuple[str, str | None]] = {
    "Amazon": ("Shopping", None),
    "Starbucks": ("Food", "Coffee"),
}
