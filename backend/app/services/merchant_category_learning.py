import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.merchant_category_preference import MerchantCategoryPreference


@dataclass
class CategorySuggestion:
    category_id: uuid.UUID
    confidence: int
    source: Literal["user_history", "global_consensus"]


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


def suggest_category(db: Session, user_id: uuid.UUID, merchant_id: uuid.UUID) -> CategorySuggestion | None:
    """Resolves a category suggestion for a merchant, scoped to one user.

    A user's own prior choice for this merchant always wins, at confidence 100.
    Otherwise, aggregates every other user's preference for this merchant by
    category name (ids are meaningless across users), picks the most common one,
    and resolves it into the requesting user's own category tree. Confidence is
    the percentage of other preference rows that picked the winning category.
    Returns None if nobody has ever categorized this merchant.
    """
    merchant_prefs = list(
        db.scalars(select(MerchantCategoryPreference).where(MerchantCategoryPreference.merchant_id == merchant_id))
    )
    own = next((pref for pref in merchant_prefs if pref.user_id == user_id), None)
    if own is not None:
        return CategorySuggestion(category_id=own.category_id, confidence=100, source="user_history")

    others = [pref for pref in merchant_prefs if pref.user_id != user_id]
    if not others:
        return None

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
        return None

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
