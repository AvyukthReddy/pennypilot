import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.merchant import Merchant, MerchantAlias
from app.services.default_merchant_aliases import DEFAULT_MERCHANT_ALIASES

# Known payment-processor/aggregator prefixes that precede the real merchant name.
_PROCESSOR_PREFIX_RE = re.compile(r"^(?:SQ|TST|PAYPAL|PP|SP)\s*\*\s*")
# ".COM*123" / ".COM/BILL" / plain ".COM" - strip the domain and anything after it.
_DOMAIN_SUFFIX_RE = re.compile(r"\.(?:COM|NET|ORG)\b.*")
# "#18273" store/reference numbers.
_HASH_STORE_NUM_RE = re.compile(r"#\d+")
# "STORE 18273" / "STORE #18273".
_STORE_WORD_NUM_RE = re.compile(r"\bSTORE\s*#?\d+\b")
# Trailing "*2X82"-style reference codes appended by card processors.
_TRAILING_REF_CODE_RE = re.compile(r"\*[A-Z0-9]+$")
# Trailing standalone numeric store numbers, e.g. "STARBUCKS 01827".
_TRAILING_DIGITS_RE = re.compile(r"\s+\d{3,}$")
_US_STATE_CODES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|"
    "NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
# Trailing "CITY ST" suffix - uses a real state-abbreviation set (not any 2 letters)
# so a token like "US" (country, not a state) is never mistaken for one. Only strips
# exactly one preceding word as the "city": an unbounded word count would greedily eat
# real merchant-name words too (e.g. "JOES PIZZA CHICAGO IL" would collapse to "JOES"
# instead of "JOES PIZZA"). This means two-word cities (e.g. "SAN FRANCISCO CA") won't
# be fully stripped; better to under-strip than corrupt the merchant name.
_TRAILING_CITY_STATE_RE = re.compile(rf"\s+[A-Z]+\s+(?:{_US_STATE_CODES})$")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_merchant_key(raw: str) -> str:
    """Deterministic tier-1 cleanup: turns a raw bank transaction description into an
    uppercase alias lookup key, stripping payment-processor prefixes, trailing store/
    reference numbers, domain-style suffixes, and trailing city+state codes.

    Examples:
        "STARBUCKS #18273 AUSTIN TX" -> "STARBUCKS"
        "STARBUCKS STORE 18273"      -> "STARBUCKS"
        "SQ *STARBUCKS"              -> "STARBUCKS"
        "STARBUCKS 01827"            -> "STARBUCKS"
        "AMAZON.COM*123"             -> "AMAZON"
        "AMZN.COM/BILL"              -> "AMZN"
        "AMZN MKTP US*2X82"          -> "AMZN MKTP US"   (needs the seed-dict tier)
        "Amazon Marketplace"         -> "AMAZON MARKETPLACE"
    """
    s = raw.strip().upper()
    s = _PROCESSOR_PREFIX_RE.sub("", s)
    s = _DOMAIN_SUFFIX_RE.sub("", s)
    s = _HASH_STORE_NUM_RE.sub("", s)
    s = _STORE_WORD_NUM_RE.sub("", s)
    s = _TRAILING_REF_CODE_RE.sub("", s)
    s = _TRAILING_DIGITS_RE.sub("", s)
    s = _TRAILING_CITY_STATE_RE.sub("", s)
    return _WHITESPACE_RE.sub(" ", s).strip()


def _title_case_candidate(normalized_key: str) -> str:
    """Turns a normalized alias key into a display-friendly candidate name for a
    newly auto-created merchant, e.g. "JOES PIZZA" -> "Joes Pizza"."""
    return normalized_key.title()


def _seed_lookup(normalized_key: str) -> str | None:
    """Longest-key-first prefix match against DEFAULT_MERCHANT_ALIASES."""
    for key in sorted(DEFAULT_MERCHANT_ALIASES, key=len, reverse=True):
        if normalized_key.startswith(key):
            return DEFAULT_MERCHANT_ALIASES[key]
    return None


def _get_or_create_merchant(db: Session, name: str) -> Merchant:
    merchant = db.scalar(select(Merchant).where(Merchant.name == name))
    if merchant is not None:
        return merchant
    merchant = Merchant(id=uuid.uuid4(), name=name)
    db.add(merchant)
    return merchant


def resolve_merchant(db: Session, raw_description: str) -> Merchant:
    """Resolves a raw bank transaction description to its canonical Merchant row.

    Algorithm: normalize (tier 1, deterministic regex) -> exact match against
    merchant_aliases (tier 2) -> hand-seeded brand dictionary, prefix match (tier 3)
    -> get-or-create a new Merchant + MerchantAlias (tier 4, self-learning) so the
    same raw string (or anything normalizing to the same key) resolves instantly next
    time via tier 2. Not wired into transaction ingestion; callers invoke this
    explicitly.
    """
    normalized = normalize_merchant_key(raw_description)
    if not normalized:
        normalized = (raw_description or "").strip().upper() or "UNKNOWN"

    existing_alias = db.scalar(select(MerchantAlias).where(MerchantAlias.alias == normalized))
    if existing_alias is not None:
        merchant = db.get(Merchant, existing_alias.merchant_id)
        if merchant is not None:
            return merchant

    canonical_name = _seed_lookup(normalized) or _title_case_candidate(normalized)
    merchant = _get_or_create_merchant(db, canonical_name)
    db.add(MerchantAlias(id=uuid.uuid4(), merchant_id=merchant.id, alias=normalized))
    db.commit()
    return merchant
