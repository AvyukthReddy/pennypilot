import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models.transaction import Transaction

client = TestClient(app)

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeSession:
    """Preloaded with exactly what the query should return, same convention
    as test_statements.py's FakeSession: this exercises the endpoint's
    response assembly, not the real WHERE-clause filtering (which is
    standard SQLAlchemy `.where()` usage, not custom logic worth re-proving
    here)."""

    def __init__(self, transactions: list[Transaction], total: int | None = None) -> None:
        self.transactions = transactions
        self.total = total if total is not None else len(transactions)

    def scalar(self, _stmt):
        return self.total

    def scalars(self, _stmt):
        return self.transactions


def _use_fake_db(session: FakeSession) -> None:
    app.dependency_overrides[get_db] = lambda: session


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)


def _make_transaction(**overrides) -> Transaction:
    defaults = dict(
        id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        transaction_date=date(2026, 7, 14),
        post_date=None,
        description="Coffee Shop",
        amount=Decimal("-4.50"),
        currency=None,
        raw_row=None,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def test_list_transactions_requires_auth() -> None:
    response = client.get("/api/transactions")
    assert response.status_code == 401


def test_list_transactions_returns_items(make_token) -> None:
    txn = _make_transaction()
    _use_fake_db(FakeSession([txn]))
    token = make_token()

    response = client.get("/api/transactions", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert body["total_pages"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["description"] == "Coffee Shop"
    assert body["items"][0]["amount"] == "-4.50"
    assert "statement_id" in body["items"][0]


def test_list_transactions_echoes_pagination_params(make_token) -> None:
    _use_fake_db(FakeSession([], total=137))
    token = make_token()

    response = client.get(
        "/api/transactions?page=3&page_size=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 3
    assert body["page_size"] == 10
    assert body["total"] == 137
    assert body["total_pages"] == 14


def test_list_transactions_accepts_statement_id_filter(make_token) -> None:
    _use_fake_db(FakeSession([]))
    token = make_token()
    statement_id = uuid.uuid4()

    response = client.get(
        f"/api/transactions?statement_id={statement_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200


def test_list_transactions_rejects_out_of_range_page_size(make_token) -> None:
    _use_fake_db(FakeSession([]))
    token = make_token()

    response = client.get(
        "/api/transactions?page_size=500",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_list_transactions_accepts_document_name_filter(make_token) -> None:
    _use_fake_db(FakeSession([]))
    token = make_token()

    response = client.get(
        "/api/transactions?document_name=chase-jan.pdf&document_name=chase-feb.pdf",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200


def test_list_transactions_accepts_type_and_date_filters(make_token) -> None:
    _use_fake_db(FakeSession([]))
    token = make_token()

    response = client.get(
        "/api/transactions?type=debit&start_date=2026-01-01&end_date=2026-01-31"
        "&sort_by=amount&sort_order=asc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
