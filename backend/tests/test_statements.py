import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models.statement import Statement

client = TestClient(app)

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeSession:
    def __init__(self, statements: list[Statement] | None = None) -> None:
        self.store: dict[uuid.UUID, Statement] = {s.id: s for s in (statements or [])}
        self.deleted: list[uuid.UUID] = []
        self.scalar_result: Statement | None = None

    def get(self, _model, pk):
        return self.store.get(pk)

    def add(self, obj: Statement) -> None:
        self.store[obj.id] = obj

    def delete(self, obj: Statement) -> None:
        self.deleted.append(obj.id)
        self.store.pop(obj.id, None)

    def commit(self) -> None:
        pass

    def refresh(self, obj: Statement) -> None:
        # Mimics what a real refresh() would pull back for server-side defaults.
        if obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)
        if obj.status is None:
            obj.status = "uploaded"

    def scalars(self, _stmt):
        return list(self.store.values())

    def scalar(self, _stmt):
        # None means "no duplicate found" for the file_hash dedup check.
        return self.scalar_result


def _use_fake_db(session: FakeSession) -> None:
    app.dependency_overrides[get_db] = lambda: session


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)


def test_list_statements_requires_auth() -> None:
    response = client.get("/api/statements")
    assert response.status_code == 401


def test_upload_statement_requires_auth() -> None:
    response = client.post(
        "/api/statements", files={"file": ("statement.pdf", b"data", "application/pdf")}
    )
    assert response.status_code == 401


def test_upload_statement_creates_row(make_token, monkeypatch) -> None:
    _use_fake_db(FakeSession())
    monkeypatch.setattr(
        "app.api.statements.upload_statement",
        lambda **kwargs: f"{kwargs['user_id']}/{kwargs['statement_id']}.pdf",
    )
    monkeypatch.setattr(
        "app.api.statements.get_statement_view_url",
        lambda **kwargs: "https://example.com/signed",
    )
    monkeypatch.setattr("app.api.statements.enqueue_parse_statement", lambda **kwargs: None)
    token = make_token()

    response = client.post(
        "/api/statements",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("statement.pdf", b"data", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "statement.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["status"] == "queued"
    assert body["size_bytes"] == 4


def test_upload_statement_rejects_duplicate_file(make_token, monkeypatch) -> None:
    existing = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="jan.pdf",
        storage_path=f"{TEST_USER_ID}/jan.pdf",
        content_type="application/pdf",
        size_bytes=4,
        status="parsed",
        file_hash="dummy-hash",
    )
    session = FakeSession([existing])
    session.scalar_result = existing
    _use_fake_db(session)
    upload_called = False

    def _fail_if_called(**kwargs):
        nonlocal upload_called
        upload_called = True
        return "should-not-be-used"

    monkeypatch.setattr("app.api.statements.upload_statement", _fail_if_called)
    token = make_token()

    response = client.post(
        "/api/statements",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("statement.pdf", b"data", "application/pdf")},
    )

    assert response.status_code == 409
    assert upload_called is False
    assert len(session.store) == 1


def test_upload_statement_enqueue_failure_leaves_uploaded_status(make_token, monkeypatch) -> None:
    _use_fake_db(FakeSession())
    monkeypatch.setattr(
        "app.api.statements.upload_statement",
        lambda **kwargs: f"{kwargs['user_id']}/{kwargs['statement_id']}.pdf",
    )

    def _raise(**kwargs):
        raise RuntimeError("supabase unreachable")

    monkeypatch.setattr("app.api.statements.get_statement_view_url", _raise)
    token = make_token()

    response = client.post(
        "/api/statements",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("statement.pdf", b"data", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"


def test_list_statements_returns_uploaded(make_token) -> None:
    statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="jan.csv",
        storage_path=f"{TEST_USER_ID}/jan.csv",
        content_type="text/csv",
        size_bytes=10,
        status="uploaded",
        created_at=datetime.now(timezone.utc),
    )
    _use_fake_db(FakeSession([statement]))
    token = make_token()

    response = client.get("/api/statements", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()[0]["filename"] == "jan.csv"


def test_view_statement_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/view")
    assert response.status_code == 401


def test_view_statement_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="uploaded",
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/view",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_view_statement_returns_signed_url(make_token, monkeypatch) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="uploaded",
    )
    _use_fake_db(FakeSession([own_statement]))
    monkeypatch.setattr(
        "app.api.statements.get_statement_view_url",
        lambda **kwargs: "https://example.com/signed",
    )
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/view", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == {"url": "https://example.com/signed"}


def test_get_statement_pages_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/pages")
    assert response.status_code == 401


def test_get_statement_pages_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        pages=[],
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/pages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_pages_returns_empty_when_not_yet_analyzed(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="queued",
        pages=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/pages", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["pages"] == []


def test_get_statement_pages_returns_persisted_pages(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        pages=[
            {
                "page_number": 1,
                "width": 612,
                "height": 792,
                "text": "STARBUCKS",
                "text_blocks": [
                    {"text": "STARBUCKS", "x": 145.0, "y": 302.5, "width": 73.3, "height": 12.0}
                ],
                "images": [],
            }
        ],
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/pages", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["pages"]) == 1
    assert body["pages"][0]["text_blocks"][0]["text"] == "STARBUCKS"


def test_get_statement_analysis_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/analysis")
    assert response.status_code == 401


def test_get_statement_analysis_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis=None,
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_analysis_returns_null_when_not_yet_classified(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["document_analysis"] is None


def test_get_statement_analysis_returns_persisted_analysis(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={
            "document_type": "bank_statement",
            "institution": "Chase",
            "account_type": "checking",
            "account_last4": "1234",
            "currency": "USD",
            "statement_start": "2026-07-01",
            "statement_end": "2026-07-31",
            "sections": [{"type": "transactions", "pages": [2, 3]}],
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()["document_analysis"]
    assert body["document_type"] == "bank_statement"
    assert body["institution"] == "Chase"
    assert body["sections"][0]["pages"] == [2, 3]


def test_get_statement_transaction_regions_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/transaction-regions")
    assert response.status_code == 401


def test_get_statement_transaction_regions_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_regions=None,
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/transaction-regions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_transaction_regions_returns_null_when_not_yet_detected(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_regions=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/transaction-regions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["transaction_regions"] is None


def test_get_statement_transaction_regions_returns_persisted_regions(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_regions={
            "transaction_regions": [
                {"page": 2, "region": [45, 180, 570, 730]},
                {"page": 3, "region": [45, 90, 570, 730]},
            ]
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/transaction-regions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    regions = response.json()["transaction_regions"]
    assert len(regions) == 2
    assert regions[0]["page"] == 2
    assert regions[0]["region"] == [45, 180, 570, 730]


def test_delete_statement_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="uploaded",
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.delete(
        f"/api/statements/{other_user_statement.id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_delete_statement_removes_own_statement(make_token, monkeypatch) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="uploaded",
    )
    session = FakeSession([own_statement])
    _use_fake_db(session)
    monkeypatch.setattr("app.api.statements.delete_statement", lambda **kwargs: None)
    token = make_token()

    response = client.delete(
        f"/api/statements/{own_statement.id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert own_statement.id in session.deleted
