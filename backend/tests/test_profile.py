import uuid

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.db import get_db
from app.main import app
from app.models.user import User

client = TestClient(app)


class FakeSession:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, User] = {}

    def get(self, model, pk):
        return self.store.get(pk)

    def add(self, obj: User) -> None:
        self.store[obj.user_id] = obj

    def commit(self) -> None:
        usernames = [p.username for p in self.store.values() if p.username]
        if len(usernames) != len(set(usernames)):
            raise IntegrityError("duplicate username", {}, Exception("unique violation"))

    def refresh(self, obj: User) -> None:
        pass

    def rollback(self) -> None:
        pass


def _use_fake_db(session: FakeSession) -> None:
    app.dependency_overrides[get_db] = lambda: session


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)


def test_profile_requires_auth() -> None:
    response = client.get("/api/profile")
    assert response.status_code == 401


def test_get_profile_defaults_when_missing(make_token) -> None:
    _use_fake_db(FakeSession())
    token = make_token()

    response = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "username": None,
        "first_name": None,
        "last_name": None,
        "country": None,
        "currency": None,
        "profile_image": None,
        "created_at": None,
        "updated_at": None,
    }


def test_update_profile_creates_then_partially_updates(make_token) -> None:
    _use_fake_db(FakeSession())
    token = make_token()
    headers = {"Authorization": f"Bearer {token}"}

    response = client.put(
        "/api/profile",
        headers=headers,
        json={"username": "avy", "first_name": "Avyukth", "country": "us", "currency": "usd"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "username": "avy",
        "first_name": "Avyukth",
        "last_name": None,
        "country": "US",
        "currency": "USD",
        "profile_image": None,
        "created_at": None,
        "updated_at": None,
    }

    response = client.put("/api/profile", headers=headers, json={"last_name": "Reddy"})
    assert response.status_code == 200
    body = response.json()
    assert body["last_name"] == "Reddy"
    assert body["username"] == "avy"


def test_update_profile_rejects_duplicate_username(make_token) -> None:
    session = FakeSession()
    other_user_id = uuid.uuid4()
    session.store[other_user_id] = User(user_id=other_user_id, username="taken")
    _use_fake_db(session)

    token = make_token()
    response = client.put(
        "/api/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "taken"},
    )

    assert response.status_code == 409
