import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.merchant import Merchant
from app.models.merchant_category_preference import MerchantCategoryPreference
from app.services.default_merchant_categories import DEFAULT_MERCHANT_CATEGORIES

# Confidence assigned to a curated seed-dictionary suggestion: lower than any real
# usage signal (a user's own choice is 100, cross-user consensus is measured), since
# this is an unmeasured, hand-curated guess rather than observed behavior.
SEEDED_DEFAULT_CONFIDENCE = 50


@dataclass
class CategorySuggestion:
    category_id: uuid.UUID
    confidence: int
    source: Literal["user_history", "global_consensus", "seeded_default"]


def _siblings(db: Session, user_id: uuid.UUID, parent_id: uuid.UUID | None) -> list[Category]:
    return list(db.scalars(select(Category).where(Category.user_id == user_id, Category.parent_id == parent_id)))


def _find_or_create_category(db: Session, user_id: uuid.UUID, name: str, parent_name: str | None) -> Category:
    """Case-insensitive find-or-create scoped to the right hierarchy level, same
    convention as categories.py's create_category (explicit id, sort_order by
    sibling count, is_default False). Recurses one level to resolve the parent
    first when a subcategory is requested.
    """
    parent_id = None
    if parent_name is not None:
        parent_id = _find_or_create_category(db, user_id, parent_name, None).id

    siblings = _siblings(db, user_id, parent_id)
    for sibling in siblings:
        if sibling.name.lower() == name.lower():
            return sibling

    category = Category(
        id=uuid.uuid4(), user_id=user_id, parent_id=parent_id, name=name,
        is_default=False, sort_order=len(siblings),
    )
    db.add(category)
    db.commit()
    return category


def _seeded_suggestion(db: Session, user_id: uuid.UUID, merchant: Merchant | None) -> CategorySuggestion | None:
    if merchant is None:
        return None
    entry = DEFAULT_MERCHANT_CATEGORIES.get(merchant.name)
    if entry is None:
        return None
    category_name, parent_name = entry
    resolved = _find_or_create_category(db, user_id, category_name, parent_name)
    return CategorySuggestion(category_id=resolved.id, confidence=SEEDED_DEFAULT_CONFIDENCE, source="seeded_default")


def suggest_category(db: Session, user_id: uuid.UUID, merchant_id: uuid.UUID) -> CategorySuggestion | None:
    """Resolves a category suggestion for a merchant, scoped to one user.

    Three tiers, in priority order: (1) the user's own prior choice for this
    merchant, if any, at confidence 100. (2) Otherwise, every other user's
    preference for this merchant, aggregated by category name (ids are meaningless
    across users), the most common one resolved into the requesting user's own
    category tree, confidence the percentage of other preference rows that picked
    it. (3) Otherwise, a curated seed-dictionary default for this merchant name, if
    one exists, at a fixed lower confidence, an unmeasured guess rather than
    observed behavior. Returns None if none of the three apply.
    """
    merchant_prefs = list(
        db.scalars(select(MerchantCategoryPreference).where(MerchantCategoryPreference.merchant_id == merchant_id))
    )
    own = next((pref for pref in merchant_prefs if pref.user_id == user_id), None)
    if own is not None:
        return CategorySuggestion(category_id=own.category_id, confidence=100, source="user_history")

    merchant = db.get(Merchant, merchant_id)
    others = [pref for pref in merchant_prefs if pref.user_id != user_id]
    if not others:
        return _seeded_suggestion(db, user_id, merchant)

    votes: Counter[tuple[str, str | None]] = Counter()
    display: dict[tuple[str, str | None], tuple[str, str | None]] = {}
    for pref in others:
        category = db.get(Category, pref.category_id)
        if category is None:
            continue
        parent = db.get(Category, category.parent_id) if category.parent_id else None
        key = (category.name.lower(), parent.name.lower() if parent else None)
        votes[key] += 1
        display.setdefault(key, (category.name, parent.name if parent else None))

    if not votes:
        return _seeded_suggestion(db, user_id, merchant)

    winning_key, winning_count = votes.most_common(1)[0]
    confidence = round(winning_count / len(others) * 100)
    winning_name, winning_parent_name = display[winning_key]

    resolved = _find_or_create_category(db, user_id, winning_name, winning_parent_name)
    return CategorySuggestion(category_id=resolved.id, confidence=confidence, source="global_consensus")


def record_preference(
    db: Session, user_id: uuid.UUID, merchant_id: uuid.UUID, category_id: uuid.UUID
) -> MerchantCategoryPreference:
    """Upserts the caller's (user, merchant) preference. Last write wins, never
    appends a second row for the same pair.
    """
    existing = db.scalar(
        select(MerchantCategoryPreference).where(
            MerchantCategoryPreference.user_id == user_id,
            MerchantCategoryPreference.merchant_id == merchant_id,
        )
    )
    if existing is not None:
        existing.category_id = category_id
        db.commit()
        db.refresh(existing)
        return existing

    pref = MerchantCategoryPreference(id=uuid.uuid4(), user_id=user_id, merchant_id=merchant_id, category_id=category_id)
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref
