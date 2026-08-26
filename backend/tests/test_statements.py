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


def test_get_statement_transaction_schema_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/transaction-schema")
    assert response.status_code == 401


def test_get_statement_transaction_schema_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_schema=None,
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/transaction-schema",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_transaction_schema_returns_null_when_not_yet_discovered(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_schema=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/transaction-schema",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["transaction_fields"] is None


def test_get_statement_transaction_schema_returns_persisted_schema(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_schema={
            "transaction_fields": {
                "transaction_date": {"source": "column_1"},
                "post_date": {"source": "column_2"},
                "description": {"source": "column_3"},
                "amount": [
                    {"source": "column_4", "semantics": "debit"},
                    {"source": "column_5", "semantics": "credit"},
                ],
                "currency": None,
            }
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/transaction-schema",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    fields = response.json()["transaction_fields"]
    assert fields["transaction_date"]["source"] == "column_1"
    assert len(fields["amount"]) == 2
    assert fields["amount"][0]["semantics"] == "debit"
    assert fields["amount"][1]["semantics"] == "credit"


def test_get_statement_transaction_verification_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/transaction-verification")
    assert response.status_code == 401


def test_get_statement_transaction_verification_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_verification=None,
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/transaction-verification",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_transaction_verification_returns_null_when_not_yet_run(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_verification=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/transaction-verification",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is None
    assert body["issues"] == []


def test_get_statement_transaction_verification_returns_persisted_report(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        transaction_verification={
            "valid": False,
            "issues": [
                {"type": "missing_transaction", "page": 3, "description": "07/18 UBER TRIP"},
            ],
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/transaction-verification",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert len(body["issues"]) == 1
    assert body["issues"][0]["type"] == "missing_transaction"
    assert body["issues"][0]["page"] == 3


def test_get_statement_analysis_includes_balance_fields(make_token) -> None:
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
            "sections": [],
            "beginning_balance": "1000.00",
            "ending_balance": "1380.00",
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    analysis = response.json()["document_analysis"]
    assert analysis["beginning_balance"] == "1000.00"
    assert analysis["ending_balance"] == "1380.00"


def test_get_statement_financial_validation_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/financial-validation")
    assert response.status_code == 401


def test_get_statement_financial_validation_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        financial_validation=None,
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/financial-validation",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_financial_validation_returns_null_when_not_yet_run(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        financial_validation=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/financial-validation",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is None
    assert body["issues"] == []
    assert body["balance_check"] is None


def test_get_statement_financial_validation_returns_persisted_report(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        financial_validation={
            "valid": False,
            "issues": [
                {"type": "balance_mismatch", "description": "Expected 1330.00, statement shows 1380.00"},
            ],
            "balance_check": {
                "beginning_balance": "1000.00",
                "net_change": "330.00",
                "expected_ending_balance": "1330.00",
                "actual_ending_balance": "1380.00",
                "reconciled": False,
            },
            "recovery_attempts": [{"page": 3, "succeeded": False}, {"page": 5, "succeeded": False}],
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/financial-validation",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["issues"][0]["type"] == "balance_mismatch"
    assert body["balance_check"]["reconciled"] is False
    assert body["recovery_attempts"] == [
        {"page": 3, "succeeded": False},
        {"page": 5, "succeeded": False},
    ]


def test_get_statement_financial_validation_defaults_recovery_attempts_when_absent(
    make_token,
) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        financial_validation={
            # A pre-Phase-9 persisted record, with no recovery_attempts key.
            "valid": True,
            "issues": [],
            "balance_check": None,
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/financial-validation",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["recovery_attempts"] == []


def test_get_statement_confidence_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/confidence")
    assert response.status_code == 401


def test_get_statement_confidence_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        confidence=None,
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/confidence",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_confidence_returns_null_when_not_yet_computed(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        confidence=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/confidence",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] is None
    assert body["status"] is None
    assert body["warnings"] == []
    assert body["breakdown"] is None


def test_get_statement_confidence_returns_persisted_score(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        confidence={
            "score": 0.667,
            "status": "unreliable",
            "warnings": ["Statement balance does not reconcile"],
            "breakdown": {
                "extraction": 1.0,
                "verification": 1.0,
                "financial_validation": 0.0,
                "balance_reconciliation": 0.0,
                "structural_consistency": 1.0,
            },
        },
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/confidence",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 0.667
    assert body["status"] == "unreliable"
    assert body["warnings"] == ["Statement balance does not reconcile"]
    assert body["breakdown"]["financial_validation"] == 0.0


def test_get_statement_currency_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/currency")
    assert response.status_code == 401


def test_get_statement_currency_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/currency",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_currency_falls_back_to_default_when_nothing_known(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis=None,
        currency=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/currency",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "USD"
    assert body["source"] == "default"
    assert body["detected_currency"] is None


def test_get_statement_currency_uses_detected_value(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "currency": "EUR"},
        currency=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/currency",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "EUR"
    assert body["source"] == "detected"
    assert body["detected_currency"] == "EUR"


def test_get_statement_currency_prefers_user_override(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "currency": "EUR"},
        currency="GBP",
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/currency",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "GBP"
    assert body["source"] == "override"
    assert body["detected_currency"] == "EUR"


def test_update_statement_currency_requires_auth() -> None:
    response = client.patch(f"/api/statements/{uuid.uuid4()}/currency", json={"currency": "GBP"})
    assert response.status_code == 401


def test_update_statement_currency_sets_override(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "currency": "EUR"},
        currency=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.patch(
        f"/api/statements/{own_statement.id}/currency",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": "gbp"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "GBP"
    assert body["source"] == "override"
    assert own_statement.currency == "GBP"


def test_update_statement_currency_clears_override(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "currency": "EUR"},
        currency="GBP",
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.patch(
        f"/api/statements/{own_statement.id}/currency",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "EUR"
    assert body["source"] == "detected"
    assert own_statement.currency is None


def test_get_statement_institution_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/institution")
    assert response.status_code == 401


def test_get_statement_institution_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/institution",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_institution_falls_back_to_default_when_nothing_known(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis=None,
        institution=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/institution",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["institution"] is None
    assert body["source"] == "default"
    assert body["detected_institution"] is None


def test_get_statement_institution_uses_detected_value(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "institution": "Chase"},
        institution=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/institution",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["institution"] == "Chase"
    assert body["source"] == "detected"
    assert body["detected_institution"] == "Chase"


def test_get_statement_institution_prefers_user_override(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "institution": "Chase"},
        institution="My Bank",
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/institution",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["institution"] == "My Bank"
    assert body["source"] == "override"
    assert body["detected_institution"] == "Chase"


def test_update_statement_institution_requires_auth() -> None:
    response = client.patch(
        f"/api/statements/{uuid.uuid4()}/institution", json={"institution": "My Bank"}
    )
    assert response.status_code == 401


def test_update_statement_institution_sets_override(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "institution": "Chase"},
        institution=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.patch(
        f"/api/statements/{own_statement.id}/institution",
        headers={"Authorization": f"Bearer {token}"},
        json={"institution": "  My   Bank  "},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["institution"] == "My Bank"
    assert body["source"] == "override"
    assert own_statement.institution == "My Bank"


def test_update_statement_institution_reset_to_null_falls_back_to_detected(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "institution": "Chase"},
        institution="My Bank",
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.patch(
        f"/api/statements/{own_statement.id}/institution",
        headers={"Authorization": f"Bearer {token}"},
        json={"institution": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["institution"] == "Chase"
    assert body["source"] == "detected"
    assert own_statement.institution is None


def test_get_statement_account_type_tags_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/account-type-tags")
    assert response.status_code == 401


def test_get_statement_account_type_tags_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/account-type-tags",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_account_type_tags_normalizes_detected_value(make_token) -> None:
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
            "account_type": "checking_and_savings",
        },
        account_type_tags=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/account-type-tags",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["account_type_tags"] == ["checking", "savings"]
    assert body["source"] == "detected"
    assert body["detected_account_type_tags"] == ["checking", "savings"]


def test_update_statement_account_type_tags_sets_override(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "account_type": "checking"},
        account_type_tags=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.patch(
        f"/api/statements/{own_statement.id}/account-type-tags",
        headers={"Authorization": f"Bearer {token}"},
        json={"account_type_tags": ["Checking", "Savings", "checking"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["account_type_tags"] == ["checking", "savings"]
    assert body["source"] == "override"
    assert own_statement.account_type_tags == ["checking", "savings"]


def test_update_statement_account_type_tags_can_be_cleared_to_empty_list(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "account_type": "checking"},
        account_type_tags=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.patch(
        f"/api/statements/{own_statement.id}/account-type-tags",
        headers={"Authorization": f"Bearer {token}"},
        json={"account_type_tags": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["account_type_tags"] == []
    assert body["source"] == "override"
    assert body["detected_account_type_tags"] == ["checking"]
    assert own_statement.account_type_tags == []


def test_update_statement_account_type_tags_reset_to_null_falls_back_to_detected(
    make_token,
) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={"document_type": "bank_statement", "account_type": "checking"},
        account_type_tags=["custom"],
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.patch(
        f"/api/statements/{own_statement.id}/account-type-tags",
        headers={"Authorization": f"Bearer {token}"},
        json={"account_type_tags": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["account_type_tags"] == ["checking"]
    assert body["source"] == "detected"
    assert own_statement.account_type_tags is None


def test_list_statements_includes_document_type_institution_and_tags(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="ingested",
        document_analysis={
            "document_type": "credit_card_statement",
            "institution": "Chase",
            "account_type": "credit_card",
        },
        institution=None,
        account_type_tags=None,
        created_at=datetime.now(timezone.utc),
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get("/api/statements", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()[0]
    assert body["document_type"] == "credit_card_statement"
    assert body["institution"] == "Chase"
    assert body["account_type_tags"] == ["credit card"]


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


def test_get_statement_progress_requires_auth() -> None:
    response = client.get(f"/api/statements/{uuid.uuid4()}/progress")
    assert response.status_code == 401


def test_get_statement_progress_rejects_other_users_statement(make_token) -> None:
    other_user_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="not-mine.pdf",
        storage_path="somewhere/not-mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="processing",
    )
    _use_fake_db(FakeSession([other_user_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{other_user_statement.id}/progress",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_statement_progress_returns_null_stage_before_processing_starts(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="uploaded",
        processing_stage=None,
        processing_detail=None,
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/progress",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["processing_stage"] is None
    assert body["processing_detail"] is None
    assert body["parse_error"] is None


def test_get_statement_progress_returns_current_stage_while_processing(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="processing",
        processing_stage="extracting",
        processing_detail="Region 2 of 3",
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/progress",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["processing_stage"] == "extracting"
    assert body["processing_detail"] == "Region 2 of 3"


def test_get_statement_progress_returns_error_state_on_failure(make_token) -> None:
    own_statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="mine.pdf",
        storage_path=f"{TEST_USER_ID}/mine.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status="failed",
        processing_stage="detecting_regions",
        processing_detail=None,
        parse_error="Could not read this PDF, it may be corrupt.",
    )
    _use_fake_db(FakeSession([own_statement]))
    token = make_token()

    response = client.get(
        f"/api/statements/{own_statement.id}/progress",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["processing_stage"] == "detecting_regions"
    assert body["parse_error"] == "Could not read this PDF, it may be corrupt."


def test_list_statements_includes_processing_stage(make_token) -> None:
    statement = Statement(
        id=uuid.uuid4(),
        user_id=uuid.UUID(TEST_USER_ID),
        filename="jan.csv",
        storage_path=f"{TEST_USER_ID}/jan.csv",
        content_type="text/csv",
        size_bytes=10,
        status="processing",
        processing_stage="understanding",
        processing_detail=None,
        created_at=datetime.now(timezone.utc),
    )
    _use_fake_db(FakeSession([statement]))
    token = make_token()

    response = client.get("/api/statements", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()[0]
    assert body["processing_stage"] == "understanding"
    assert body["processing_detail"] is None
