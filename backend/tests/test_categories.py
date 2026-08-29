import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models.category import Category
from app.services.default_categories import DEFAULT_CATEGORIES

client = TestClient(app)

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"


def _eval_clause(clause, category: Category) -> bool:
    clauses = getattr(clause, "clauses", None)
    if clauses is not None:
        return all(_eval_clause(c, category) for c in clauses)
    attr = clause.left.key
    right = clause.right
    expected = None if isinstance(right, sa.sql.elements.Null) else right.value
    return getattr(category, attr) == expected


class FakeSession:
    """Same convention as test_statements.py's FakeSession, extended with a
    where-clause evaluator: the categories endpoints filter by user_id/
    parent_id in ways that matter for the business logic under test (sibling
    scoping for duplicate-name checks, sort_order counts, reorder
    membership), unlike the read-only endpoints in test_statements.py."""

    def __init__(self, categories: list[Category] | None = None) -> None:
        self.store: dict[uuid.UUID, Category] = {c.id: c for c in (categories or [])}

    def get(self, _model, pk):
        return self.store.get(pk)

    def add(self, obj: Category) -> None:
        self.store[obj.id] = obj

    def delete(self, obj: Category) -> None:
        self.store.pop(obj.id, None)

    def commit(self) -> None:
        pass

    def refresh(self, _obj: Category) -> None:
        pass

    def scalars(self, stmt):
        where = stmt.whereclause
        return [c for c in self.store.values() if where is None or _eval_clause(where, c)]


def _use_fake_db(session: FakeSession) -> None:
    app.dependency_overrides[get_db] = lambda: session


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)


def _make_category(**overrides) -> Category:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        parent_id=None,
        name="Groceries",
        is_default=False,
        sort_order=0,
    )
    defaults.update(overrides)
    return Category(**defaults)


def _auth(make_token, sub: str = TEST_USER_ID) -> dict:
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def test_list_categories_requires_auth() -> None:
    response = client.get("/api/categories")
    assert response.status_code == 401


def test_list_categories_seeds_defaults_when_empty(make_token) -> None:
    _use_fake_db(FakeSession([]))
    response = client.get("/api/categories", headers=_auth(make_token))
    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == [c["name"] for c in DEFAULT_CATEGORIES]
    assert body[0]["is_default"] is True
    assert [s["name"] for s in body[0]["subcategories"]] == DEFAULT_CATEGORIES[0]["subcategories"]


def test_list_categories_does_not_reseed_when_categories_exist(make_token) -> None:
    existing = _make_category(name="Custom Top Level")
    _use_fake_db(FakeSession([existing]))
    response = client.get("/api/categories", headers=_auth(make_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Custom Top Level"


def test_create_top_level_category(make_token) -> None:
    _use_fake_db(FakeSession([]))
    response = client.post(
        "/api/categories", json={"name": "Custom"}, headers=_auth(make_token)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Custom"
    assert body["parent_id"] is None
    assert body["is_default"] is False
    assert body["sort_order"] == 0


def test_create_subcategory(make_token) -> None:
    parent = _make_category(name="Food")
    _use_fake_db(FakeSession([parent]))
    response = client.post(
        "/api/categories",
        json={"name": "Snacks", "parent_id": str(parent.id)},
        headers=_auth(make_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["parent_id"] == str(parent.id)
    assert body["subcategories"] is None


def test_create_subcategory_under_subcategory_rejected(make_token) -> None:
    top = _make_category(name="Food")
    sub = _make_category(id=uuid.uuid4(), name="Snacks", parent_id=top.id)
    _use_fake_db(FakeSession([top, sub]))
    response = client.post(
        "/api/categories",
        json={"name": "Chips", "parent_id": str(sub.id)},
        headers=_auth(make_token),
    )
    assert response.status_code == 400


def test_create_duplicate_name_rejected(make_token) -> None:
    existing = _make_category(name="Groceries")
    _use_fake_db(FakeSession([existing]))
    response = client.post(
        "/api/categories", json={"name": "groceries"}, headers=_auth(make_token)
    )
    assert response.status_code == 409


def test_create_category_parent_not_owned(make_token) -> None:
    other_users_parent = _make_category(user_id=uuid.UUID(OTHER_USER_ID), name="Not yours")
    _use_fake_db(FakeSession([other_users_parent]))
    response = client.post(
        "/api/categories",
        json={"name": "Sub", "parent_id": str(other_users_parent.id)},
        headers=_auth(make_token),
    )
    assert response.status_code == 404


def test_update_category_rename(make_token) -> None:
    category = _make_category(name="Old Name")
    _use_fake_db(FakeSession([category]))
    response = client.patch(
        f"/api/categories/{category.id}", json={"name": "New Name"}, headers=_auth(make_token)
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_update_category_duplicate_name_rejected(make_token) -> None:
    a = _make_category(name="Groceries")
    b = _make_category(id=uuid.uuid4(), name="Dining")
    _use_fake_db(FakeSession([a, b]))
    response = client.patch(
        f"/api/categories/{b.id}", json={"name": "groceries"}, headers=_auth(make_token)
    )
    assert response.status_code == 409


def test_update_category_not_owned(make_token) -> None:
    other = _make_category(user_id=uuid.UUID(OTHER_USER_ID))
    _use_fake_db(FakeSession([other]))
    response = client.patch(
        f"/api/categories/{other.id}", json={"name": "Hijacked"}, headers=_auth(make_token)
    )
    assert response.status_code == 404


def test_delete_category(make_token) -> None:
    category = _make_category()
    session = FakeSession([category])
    _use_fake_db(session)
    response = client.delete(f"/api/categories/{category.id}", headers=_auth(make_token))
    assert response.status_code == 200
    assert response.json() == {"id": str(category.id)}
    assert category.id not in session.store


def test_reorder_categories(make_token) -> None:
    first = _make_category(name="A", sort_order=0)
    second = _make_category(id=uuid.uuid4(), name="B", sort_order=1)
    _use_fake_db(FakeSession([first, second]))
    response = client.patch(
        "/api/categories/reorder",
        json={"parent_id": None, "ordered_ids": [str(second.id), str(first.id)]},
        headers=_auth(make_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(second.id), str(first.id)]


def test_reorder_categories_mismatched_ids_rejected(make_token) -> None:
    first = _make_category(name="A")
    _use_fake_db(FakeSession([first]))
    response = client.patch(
        "/api/categories/reorder",
        json={"parent_id": None, "ordered_ids": [str(uuid.uuid4())]},
        headers=_auth(make_token),
    )
    assert response.status_code == 400
