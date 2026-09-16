import uuid

import sqlalchemy as sa

from app.models.category import Category
from app.models.merchant_category_preference import MerchantCategoryPreference
from app.services.merchant_category_learning import record_preference, suggest_category

USER_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
USER_B = uuid.UUID("22222222-2222-4222-8222-222222222222")
USER_C = uuid.UUID("33333333-3333-4333-8333-333333333333")
USER_D = uuid.UUID("44444444-4444-4444-8444-444444444444")
MERCHANT_ID = uuid.uuid4()


def _eval_clause(clause, obj) -> bool:
    clauses = getattr(clause, "clauses", None)
    if clauses is not None:
        return all(_eval_clause(c, obj) for c in clauses)
    attr = clause.left.key
    right = clause.right
    expected = None if isinstance(right, sa.sql.elements.Null) else right.value
    return getattr(obj, attr) == expected


class FakeSession:
    """Same convention as test_categories.py's FakeSession, extended to cover two
    related tables (categories + merchant_category_preferences)."""

    def __init__(self, categories=None, preferences=None) -> None:
        self.categories: dict[uuid.UUID, Category] = {c.id: c for c in (categories or [])}
        self.preferences: dict[uuid.UUID, MerchantCategoryPreference] = {p.id: p for p in (preferences or [])}

    def _store_for(self, model):
        return self.categories if model is Category else self.preferences

    def get(self, model, pk):
        return self._store_for(model).get(pk)

    def add(self, obj) -> None:
        self._store_for(type(obj))[obj.id] = obj

    def commit(self) -> None:
        pass

    def refresh(self, _obj) -> None:
        pass

    def scalars(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        where = stmt.whereclause
        return [o for o in self._store_for(entity).values() if where is None or _eval_clause(where, o)]

    def scalar(self, stmt):
        rows = self.scalars(stmt)
        return rows[0] if rows else None


def _make_category(**overrides) -> Category:
    defaults = dict(
        id=uuid.uuid4(), user_id=USER_A, parent_id=None, name="Groceries", is_default=False, sort_order=0,
    )
    defaults.update(overrides)
    return Category(**defaults)


def _make_preference(**overrides) -> MerchantCategoryPreference:
    defaults = dict(id=uuid.uuid4(), user_id=USER_A, merchant_id=MERCHANT_ID, category_id=uuid.uuid4())
    defaults.update(overrides)
    return MerchantCategoryPreference(**defaults)


def test_suggest_category_returns_none_when_no_preferences_exist() -> None:
    session = FakeSession()
    assert suggest_category(session, USER_A, MERCHANT_ID) is None


def test_suggest_category_returns_user_history_when_own_preference_exists() -> None:
    food = _make_category(name="Food")
    coffee = _make_category(name="Coffee", parent_id=food.id)
    pref = _make_preference(user_id=USER_A, category_id=coffee.id)
    session = FakeSession([food, coffee], [pref])

    suggestion = suggest_category(session, USER_A, MERCHANT_ID)
    assert suggestion.category_id == coffee.id
    assert suggestion.confidence == 100
    assert suggestion.source == "user_history"


def test_suggest_category_global_consensus_computes_percentage() -> None:
    # Three other users have categorized this merchant: two picked "Coffee" under
    # "Food" (their own distinct rows), one picked top-level "Business Meals".
    b_food = _make_category(user_id=USER_B, name="Food")
    b_coffee = _make_category(user_id=USER_B, name="Coffee", parent_id=b_food.id)
    c_food = _make_category(user_id=USER_C, name="Food")
    c_coffee = _make_category(user_id=USER_C, name="Coffee", parent_id=c_food.id)
    d_business = _make_category(user_id=USER_D, name="Business Meals")

    prefs = [
        _make_preference(user_id=USER_B, category_id=b_coffee.id),
        _make_preference(user_id=USER_C, category_id=c_coffee.id),
        _make_preference(user_id=USER_D, category_id=d_business.id),
    ]
    session = FakeSession([b_food, b_coffee, c_food, c_coffee, d_business], prefs)

    suggestion = suggest_category(session, USER_A, MERCHANT_ID)
    assert suggestion.confidence == 67
    assert suggestion.source == "global_consensus"

    resolved = session.categories[suggestion.category_id]
    assert resolved.user_id == USER_A
    assert resolved.name == "Coffee"
    assert resolved not in (b_coffee, c_coffee)


def test_suggest_category_reuses_existing_category_instead_of_duplicating() -> None:
    a_food = _make_category(user_id=USER_A, name="Food")
    a_coffee = _make_category(user_id=USER_A, name="Coffee", parent_id=a_food.id)
    b_food = _make_category(user_id=USER_B, name="Food")
    b_coffee = _make_category(user_id=USER_B, name="Coffee", parent_id=b_food.id)
    pref = _make_preference(user_id=USER_B, category_id=b_coffee.id)
    session = FakeSession([a_food, a_coffee, b_food, b_coffee], [pref])

    before_count = len(session.categories)
    suggestion = suggest_category(session, USER_A, MERCHANT_ID)
    assert suggestion.category_id == a_coffee.id
    assert len(session.categories) == before_count


def test_suggest_category_distinguishes_top_level_from_subcategory_same_name() -> None:
    b_food_top = _make_category(user_id=USER_B, name="Food")
    c_food_top = _make_category(user_id=USER_C, name="Food")
    d_restaurants = _make_category(user_id=USER_D, name="Restaurants")
    d_food_sub = _make_category(user_id=USER_D, name="Food", parent_id=d_restaurants.id)

    prefs = [
        _make_preference(user_id=USER_B, category_id=b_food_top.id),
        _make_preference(user_id=USER_C, category_id=c_food_top.id),
        _make_preference(user_id=USER_D, category_id=d_food_sub.id),
    ]
    session = FakeSession([b_food_top, c_food_top, d_restaurants, d_food_sub], prefs)

    suggestion = suggest_category(session, USER_A, MERCHANT_ID)
    assert suggestion.confidence == 67

    resolved = session.categories[suggestion.category_id]
    assert resolved.parent_id is None
    assert resolved.name == "Food"


def test_record_preference_inserts_new_row_when_none_exists() -> None:
    session = FakeSession()
    category_id = uuid.uuid4()
    pref = record_preference(session, USER_A, MERCHANT_ID, category_id)
    assert pref.category_id == category_id
    assert len(session.preferences) == 1


def test_record_preference_updates_existing_row_in_place() -> None:
    original_category_id = uuid.uuid4()
    existing = _make_preference(user_id=USER_A, category_id=original_category_id)
    session = FakeSession(preferences=[existing])

    new_category_id = uuid.uuid4()
    pref = record_preference(session, USER_A, MERCHANT_ID, new_category_id)
    assert pref.id == existing.id
    assert pref.category_id == new_category_id
    assert len(session.preferences) == 1
