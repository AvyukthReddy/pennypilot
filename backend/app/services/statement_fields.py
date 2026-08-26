import re

from app.models.statement import Statement

# Splits a raw account_type string into individual tags: "," "&" "+" "/" and the
# whole word "and" (so it doesn't fire inside a real word). A lone underscore-joined
# phrase like "credit_card" is NOT split - underscores are converted to spaces
# first so "credit_card" and "credit card" converge on the same normalized tag.
_TAG_SPLIT_RE = re.compile(r"[,&+/]|\band\b")


def normalize_account_type_tags(raw: str | None) -> list[str]:
    """Turns a raw, unconstrained AI account_type string into a clean list of
    lowercase tags.

    Examples:
        "credit_card"          -> ["credit card"]
        "credit card"          -> ["credit card"]
        "checking_and_savings" -> ["checking", "savings"]
        "Checking & Savings"   -> ["checking", "savings"]
        None / "" / "   "      -> []
    """
    if not raw or not raw.strip():
        return []

    normalized = re.sub(r"\s+", " ", raw.strip().lower().replace("_", " ")).strip()

    tags: list[str] = []
    seen: set[str] = set()
    for piece in _TAG_SPLIT_RE.split(normalized):
        tag = re.sub(r"\s+", " ", piece).strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def resolve_institution(statement: Statement) -> tuple[str | None, str, str | None]:
    """Returns (effective_institution, source, detected_institution). Same
    override/detected/default precedence as statements.py's _resolve_currency."""
    detected = (
        statement.document_analysis.get("institution") if statement.document_analysis else None
    )
    if statement.institution:
        return statement.institution, "override", detected
    if detected:
        return detected, "detected", detected
    return None, "default", detected


def resolve_account_type_tags(statement: Statement) -> tuple[list[str], str, list[str]]:
    """Returns (effective_tags, source, detected_tags). statement.account_type_tags
    being None means "no override, use detected"; an explicit [] means the user
    cleared every tag and detection must NOT be used as a fallback."""
    detected = normalize_account_type_tags(
        statement.document_analysis.get("account_type") if statement.document_analysis else None
    )
    if statement.account_type_tags is not None:
        return statement.account_type_tags, "override", detected
    if detected:
        return detected, "detected", detected
    return [], "default", detected
