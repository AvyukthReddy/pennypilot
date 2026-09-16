import uuid

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from tests.test_merchant_normalization import FakeSession

client = TestClient(app)

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


def _use_fake_db(session: FakeSession) -> None:
    app.dependency_overrides[get_db] = lambda: session


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)


def _auth(make_token, sub: str = TEST_USER_ID) -> dict:
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def test_normalize_merchant_requires_auth() -> None:
    response = client.post("/api/merchants/normalize", json={"description": "SQ *STARBUCKS"})
    assert response.status_code == 401


def test_normalize_merchant_resolves_known_variant(make_token) -> None:
    _use_fake_db(FakeSession())
    response = client.post(
        "/api/merchants/normalize",
        json={"description": "SQ *STARBUCKS"},
        headers=_auth(make_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Starbucks"
    assert body["default_category_id"] is None


def test_normalize_merchant_repeat_call_reuses_merchant(make_token) -> None:
    session = FakeSession()
    _use_fake_db(session)
    first = client.post(
        "/api/merchants/normalize",
        json={"description": "STARBUCKS #18273 AUSTIN TX"},
        headers=_auth(make_token),
    )
    second = client.post(
        "/api/merchants/normalize",
        json={"description": "STARBUCKS STORE 18273"},
        headers=_auth(make_token),
    )
    assert first.json()["id"] == second.json()["id"]
    assert uuid.UUID(first.json()["id"])
