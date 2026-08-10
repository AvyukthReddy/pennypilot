from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TEST_USER_ID

client = TestClient(app)


def test_me_requires_auth() -> None:
    response = client.get("/api/me")
    assert response.status_code == 401


def test_me_rejects_invalid_token() -> None:
    response = client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_me_rejects_wrong_audience(make_token) -> None:
    token = make_token(aud="some-other-audience")
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_returns_user_for_valid_token(make_token) -> None:
    token = make_token()
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"id": TEST_USER_ID, "email": "test@example.com"}
