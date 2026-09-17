import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models.category import Category
from app.models.merchant import Merchant, MerchantAlias
from app.models.merchant_category_preference import MerchantCategoryPreference
from app.models.transaction import Transaction

client = TestClient(app)

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
USER_C = "33333333-3333-4333-8333-333333333333"
USER_D = "44444444-4444-4444-8444-444444444444"

MODELS = (Transaction, Category, Merchant, MerchantAlias, MerchantCategoryPreference)


def _eval_clause(clause, obj) -> bool:
    clauses = getattr(clause, "clauses", None)
    if clauses is not None:
        return all(_eval_clause(c, obj) for c in clauses)
    attr = clause.left.key
    right = clause.right
    expected = None if isinstance(right, sa.sql.elements.Null) else right.value
    return getattr(obj, attr) == expected


class FakeSession:
    def __init__(self, rows: list | None = None) -> None:
        self.stores: dict[type, dict[uuid.UUID, object]] = {model: {} for model in MODELS}
        for row in rows or []:
            self.stores[type(row)][row.id] = row

    def get(self, model, pk):
        return self.stores[model].get(pk)

    def add(self, obj) -> None:
        self.stores[type(obj)][obj.id] = obj

    def commit(self) -> None:
        pass

    def refresh(self, _obj) -> None:
        pass

    def scalars(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        where = stmt.whereclause
        return [o for o in self.stores[entity].values() if where is None or _eval_clause(where, o)]

    def scalar(self, stmt):
        rows = self.scalars(stmt)
        return rows[0] if rows else None


def _use_fake_db(session: FakeSession) -> None:
    app.dependency_overrides[get_db] = lambda: session


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)


def _auth(make_token, sub: str) -> dict:
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def _make_transaction(**overrides) -> Transaction:
    defaults = dict(
        id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        user_id=uuid.UUID(USER_A),
        transaction_date=date(2026, 9, 1),
        post_date=None,
        description="STARBUCKS #18273 AUSTIN TX",
        amount=Decimal("-4.50"),
        currency="USD",
        merchant_id=None,
        category_id=None,
        raw_row=None,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def _make_category(**overrides) -> Category:
    defaults = dict(
        id=uuid.uuid4(), user_id=uuid.UUID(USER_A), parent_id=None, name="Groceries",
        is_default=False, sort_order=0,
    )
    defaults.update(overrides)
    return Category(**defaults)


def test_get_category_suggestion_requires_auth() -> None:
    _use_fake_db(FakeSession())
    response = client.get(f"/api/transactions/{uuid.uuid4()}/category-suggestion")
    assert response.status_code == 401


def test_patch_category_requires_auth() -> None:
    _use_fake_db(FakeSession())
    response = client.patch(
        f"/api/transactions/{uuid.uuid4()}/category", json={"category_id": str(uuid.uuid4())}
    )
    assert response.status_code == 401


def test_patch_category_404_for_other_users_transaction(make_token) -> None:
    txn = _make_transaction(user_id=uuid.UUID(USER_A))
    category = _make_category(user_id=uuid.UUID(USER_B))
    _use_fake_db(FakeSession([txn, category]))
    response = client.patch(
        f"/api/transactions/{txn.id}/category",
        json={"category_id": str(category.id)},
        headers=_auth(make_token, USER_B),
    )
    assert response.status_code == 404


def test_patch_category_404_for_unowned_category(make_token) -> None:
    txn = _make_transaction(user_id=uuid.UUID(USER_A))
    category = _make_category(user_id=uuid.UUID(USER_B))
    _use_fake_db(FakeSession([txn, category]))
    response = client.patch(
        f"/api/transactions/{txn.id}/category",
        json={"category_id": str(category.id)},
        headers=_auth(make_token, USER_A),
    )
    assert response.status_code == 404


def test_get_category_suggestion_404_for_other_users_transaction(make_token) -> None:
    txn = _make_transaction(user_id=uuid.UUID(USER_A))
    _use_fake_db(FakeSession([txn]))
    response = client.get(
        f"/api/transactions/{txn.id}/category-suggestion", headers=_auth(make_token, USER_B)
    )
    assert response.status_code == 404


def test_get_category_suggestion_returns_null_when_nobody_has_categorized_merchant(make_token) -> None:
    txn = _make_transaction(description="SOME BRAND NEW MERCHANT #999")
    _use_fake_db(FakeSession([txn]))
    response = client.get(
        f"/api/transactions/{txn.id}/category-suggestion", headers=_auth(make_token, USER_A)
    )
    assert response.status_code == 200
    assert response.json() is None


def test_patch_category_assigns_and_records_preference(make_token) -> None:
    food = _make_category(user_id=uuid.UUID(USER_A), name="Food")
    coffee = _make_category(user_id=uuid.UUID(USER_A), name="Coffee", parent_id=food.id)
    txn = _make_transaction(description="STARBUCKS #18273 AUSTIN TX")
    session = FakeSession([food, coffee, txn])
    _use_fake_db(session)

    response = client.patch(
        f"/api/transactions/{txn.id}/category",
        json={"category_id": str(coffee.id)},
        headers=_auth(make_token, USER_A),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["category_id"] == str(coffee.id)
    assert body["merchant_id"] is not None

    prefs = list(session.stores[MerchantCategoryPreference].values())
    assert len(prefs) == 1
    assert prefs[0].user_id == uuid.UUID(USER_A)
    assert prefs[0].category_id == coffee.id


def test_get_category_suggestion_user_history_for_second_transaction_same_merchant(make_token) -> None:
    food = _make_category(user_id=uuid.UUID(USER_A), name="Food")
    coffee = _make_category(user_id=uuid.UUID(USER_A), name="Coffee", parent_id=food.id)
    txn1 = _make_transaction(description="STARBUCKS #18273 AUSTIN TX")
    txn2 = _make_transaction(description="SQ *STARBUCKS")
    session = FakeSession([food, coffee, txn1, txn2])
    _use_fake_db(session)

    assign = client.patch(
        f"/api/transactions/{txn1.id}/category",
        json={"category_id": str(coffee.id)},
        headers=_auth(make_token, USER_A),
    )
    assert assign.status_code == 200

    response = client.get(
        f"/api/transactions/{txn2.id}/category-suggestion", headers=_auth(make_token, USER_A)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 100
    assert body["source"] == "user_history"
    assert body["category_id"] == str(coffee.id)


def test_get_category_suggestion_global_consensus_for_new_user(make_token) -> None:
    a_food = _make_category(user_id=uuid.UUID(USER_A), name="Food")
    a_coffee = _make_category(user_id=uuid.UUID(USER_A), name="Coffee", parent_id=a_food.id)
    c_food = _make_category(user_id=uuid.UUID(USER_C), name="Food")
    c_coffee = _make_category(user_id=uuid.UUID(USER_C), name="Coffee", parent_id=c_food.id)

    txn_a = _make_transaction(user_id=uuid.UUID(USER_A), description="STARBUCKS #18273 AUSTIN TX")
    txn_c = _make_transaction(user_id=uuid.UUID(USER_C), description="STARBUCKS STORE 18273")
    txn_b = _make_transaction(user_id=uuid.UUID(USER_B), description="STARBUCKS 01827")

    session = FakeSession([a_food, a_coffee, c_food, c_coffee, txn_a, txn_c, txn_b])
    _use_fake_db(session)

    for txn, category in ((txn_a, a_coffee), (txn_c, c_coffee)):
        response = client.patch(
            f"/api/transactions/{txn.id}/category",
            json={"category_id": str(category.id)},
            headers=_auth(make_token, str(txn.user_id)),
        )
        assert response.status_code == 200

    response = client.get(
        f"/api/transactions/{txn_b.id}/category-suggestion", headers=_auth(make_token, USER_B)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "global_consensus"
    assert body["confidence"] == 100

    resolved_id = uuid.UUID(body["category_id"])
    resolved = session.stores[Category][resolved_id]
    assert resolved.user_id == uuid.UUID(USER_B)
    assert resolved.name == "Coffee"
    assert resolved.id not in (a_coffee.id, c_coffee.id)


def test_patch_category_override_flips_to_user_history(make_token) -> None:
    a_food = _make_category(user_id=uuid.UUID(USER_A), name="Food")
    a_coffee = _make_category(user_id=uuid.UUID(USER_A), name="Coffee", parent_id=a_food.id)
    b_business = _make_category(user_id=uuid.UUID(USER_B), name="Business Meals")

    txn_a = _make_transaction(user_id=uuid.UUID(USER_A), description="STARBUCKS #18273 AUSTIN TX")
    txn_b_1 = _make_transaction(user_id=uuid.UUID(USER_B), description="STARBUCKS STORE 18273")
    txn_b_2 = _make_transaction(user_id=uuid.UUID(USER_B), description="SQ *STARBUCKS")

    session = FakeSession([a_food, a_coffee, b_business, txn_a, txn_b_1, txn_b_2])
    _use_fake_db(session)

    client.patch(
        f"/api/transactions/{txn_a.id}/category",
        json={"category_id": str(a_coffee.id)},
        headers=_auth(make_token, USER_A),
    )
    client.patch(
        f"/api/transactions/{txn_b_1.id}/category",
        json={"category_id": str(b_business.id)},
        headers=_auth(make_token, USER_B),
    )

    response = client.get(
        f"/api/transactions/{txn_b_2.id}/category-suggestion", headers=_auth(make_token, USER_B)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 100
    assert body["source"] == "user_history"
    assert body["category_id"] == str(b_business.id)


def test_patch_category_reassignment_updates_not_duplicates_preference(make_token) -> None:
    food = _make_category(user_id=uuid.UUID(USER_A), name="Food")
    coffee = _make_category(user_id=uuid.UUID(USER_A), name="Coffee", parent_id=food.id)
    other = _make_category(user_id=uuid.UUID(USER_A), name="Business Meals")

    txn1 = _make_transaction(description="STARBUCKS #18273 AUSTIN TX")
    txn2 = _make_transaction(description="STARBUCKS 01827")
    session = FakeSession([food, coffee, other, txn1, txn2])
    _use_fake_db(session)

    client.patch(
        f"/api/transactions/{txn1.id}/category",
        json={"category_id": str(coffee.id)},
        headers=_auth(make_token, USER_A),
    )
    client.patch(
        f"/api/transactions/{txn2.id}/category",
        json={"category_id": str(other.id)},
        headers=_auth(make_token, USER_A),
    )

    prefs = list(session.stores[MerchantCategoryPreference].values())
    assert len(prefs) == 1
    assert prefs[0].category_id == other.id


def test_get_category_suggestion_returns_seeded_default_for_new_merchant(make_token) -> None:
    txn = _make_transaction(description="AMZN MKTP US*2X82")
    session = FakeSession([txn])
    _use_fake_db(session)

    response = client.get(
        f"/api/transactions/{txn.id}/category-suggestion", headers=_auth(make_token, USER_A)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "seeded_default"
    assert body["confidence"] == 50

    resolved_id = uuid.UUID(body["category_id"])
    resolved = session.stores[Category][resolved_id]
    assert resolved.user_id == uuid.UUID(USER_A)
    assert resolved.name == "Shopping"
