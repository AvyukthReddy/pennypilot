"""Hand-seeded known brand mappings used by merchant_normalization.py's
resolve_merchant as a fallback tier when a description's tier-1 regex-normalized key
doesn't land on an exact merchant_aliases row. Covers brands whose raw description
varies more than trailing noise alone accounts for (e.g. "AMZN MKTP", "AMZN", and
"AMAZON.COM" all meaning Amazon, but not sharing one normalized string). Keys are
matched as a prefix against the tier-1-normalized key, longest key first, so a more
specific key wins over a shorter generic one.
"""

DEFAULT_MERCHANT_ALIASES: dict[str, str] = {
    "AMZN MKTP": "Amazon",
    "AMAZON.COM": "Amazon",
    "AMZN": "Amazon",
    "AMAZON": "Amazon",
}
