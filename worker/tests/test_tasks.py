import io
import uuid

import httpx
from reportlab.pdfgen import canvas

import worker.tasks as tasks
from worker.document_analysis import DocumentAnalysis
from worker.models import StatementRow
from worker.transaction_regions import TransactionRegionDetection

VALID_ANALYSIS = DocumentAnalysis(
    document_type="bank_statement",
    institution="Chase",
    account_type="checking",
    account_last4="1234",
    currency="USD",
    statement_start="2026-07-01",
    statement_end="2026-07-31",
    sections=[{"type": "transactions", "pages": [1]}],
)

ANALYSIS_WITHOUT_TRANSACTIONS = DocumentAnalysis(
    document_type="bank_statement",
    sections=[{"type": "account_summary", "pages": [1]}],
)

VALID_REGIONS = TransactionRegionDetection(
    transaction_regions=[{"page": 1, "region": [45, 180, 570, 730]}],
)


class _FakeUnderstandingService:
    """Stand-in for DocumentUnderstandingService — no real network call.
    `calls` is a shared list so tests can assert whether it ran at all."""

    def __init__(self, calls: list, result: DocumentAnalysis | None = None, error: Exception | None = None):
        self._calls = calls
        self._result = result
        self._error = error

    def analyze(self, document):
        self._calls.append(document)
        if self._error:
            raise self._error
        return self._result


def _patch_understanding(monkeypatch, result=None, error=None):
    calls: list = []
    monkeypatch.setattr(
        tasks,
        "DocumentUnderstandingService",
        lambda: _FakeUnderstandingService(calls, result=result, error=error),
    )
    return calls


class _FakeRegionDetectionService:
    """Stand-in for TransactionRegionDetectionService — no real network call."""

    def __init__(
        self,
        calls: list,
        result: TransactionRegionDetection | None = None,
        error: Exception | None = None,
    ):
        self._calls = calls
        self._result = result
        self._error = error

    def detect(self, document, document_analysis):
        self._calls.append((document, document_analysis))
        if self._error:
            raise self._error
        return self._result


def _patch_region_detection(monkeypatch, result=None, error=None):
    calls: list = []
    monkeypatch.setattr(
        tasks,
        "TransactionRegionDetectionService",
        lambda: _FakeRegionDetectionService(calls, result=result, error=error),
    )
    return calls


class FakeTaskSession:
    def __init__(self, statement: StatementRow) -> None:
        self.statement = statement
        self.rolled_back = False

    def get(self, model, pk):
        if model is StatementRow and pk == self.statement.id:
            return self.statement
        return None

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        pass


def _make_statement(content_type: str) -> StatementRow:
    return StatementRow(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="statement.pdf",
        content_type=content_type,
        status="queued",
        parse_error=None,
        file_hash="dummy-hash",
    )


def _run_task(monkeypatch, statement: StatementRow, response_content: bytes | Exception):
    session = FakeTaskSession(statement)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    def _fake_get(url, timeout=60):
        if isinstance(response_content, Exception):
            raise response_content
        return httpx.Response(200, content=response_content, request=httpx.Request("GET", url))

    monkeypatch.setattr(tasks.httpx, "get", _fake_get)
    tasks.parse_statement(str(statement.id), "https://example.com/signed?token=SECRET")
    return session


def _make_pdf(pages: int = 3) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(pages):
        c.drawString(72, 750, "07/14/2026   Coffee and pastries   $5.75")
        c.drawString(72, 730, "07/15/2026   Monthly subscription   $12.99")
        c.showPage()
    c.save()
    return buf.getvalue()


def _make_blank_pdf(pages: int = 2) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(pages):
        c.showPage()
    c.save()
    return buf.getvalue()


def test_parse_statement_pdf_happy_path(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    calls = _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    region_calls = _patch_region_detection(monkeypatch, result=VALID_REGIONS)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.page_count == 3
    assert statement.parser_version == tasks.INGESTION_VERSION
    assert statement.parse_error is None
    assert statement.needs_ocr is False

    assert len(statement.pages) == 3
    first_page = statement.pages[0]
    assert first_page["page_number"] == 1
    assert first_page["text_blocks"]
    assert first_page["text_blocks"][0]["text"] == "07/14/2026 Coffee and pastries $5.75"

    assert len(calls) == 1
    assert statement.document_analysis["document_type"] == "bank_statement"
    assert statement.document_analysis["institution"] == "Chase"

    assert len(region_calls) == 1
    assert statement.transaction_regions["transaction_regions"][0]["page"] == 1


def test_parse_statement_document_understanding_failure_is_non_fatal(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, error=RuntimeError("model unreachable"))

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.document_analysis is None
    # No document_analysis at all ⇒ region detection is never even reached.
    assert statement.transaction_regions is None


def test_parse_statement_region_detection_failure_is_non_fatal(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, error=RuntimeError("model unreachable"))

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.document_analysis is not None
    assert statement.transaction_regions is None


def test_parse_statement_skips_region_detection_without_transactions_section(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=ANALYSIS_WITHOUT_TRANSACTIONS)
    region_calls = _patch_region_detection(monkeypatch, result=VALID_REGIONS)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.document_analysis is not None
    assert region_calls == []
    assert statement.transaction_regions is None


def test_parse_statement_scanned_pdf_flagged_not_failed(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    calls = _patch_understanding(monkeypatch, result=VALID_ANALYSIS)

    _run_task(monkeypatch, statement, _make_blank_pdf(pages=2))

    assert statement.status == "ingested"
    assert statement.page_count == 2
    assert statement.needs_ocr is True
    assert statement.parse_error is None
    assert len(statement.pages) == 2
    assert statement.pages[0]["text_blocks"] == []
    # Scanned/no-text documents skip understanding entirely — no point
    # classifying a document with nothing extracted from it.
    assert calls == []
    assert statement.document_analysis is None


def test_parse_statement_csv_happy_path(monkeypatch) -> None:
    statement = _make_statement("text/csv")
    csv_bytes = b"Date,Description,Amount\n07/14/2026,Coffee,-4.50\n"
    calls = _patch_understanding(monkeypatch, result=VALID_ANALYSIS)

    _run_task(monkeypatch, statement, csv_bytes)

    assert calls == []
    assert statement.document_analysis is None
    assert statement.status == "ingested"
    assert statement.page_count is None
    assert statement.parser_version == tasks.INGESTION_VERSION
    assert statement.needs_ocr is False
    assert statement.pages == []


def test_parse_statement_download_failure_redacts_message(monkeypatch) -> None:
    statement = _make_statement("application/pdf")

    _run_task(monkeypatch, statement, RuntimeError("connection refused to https://signed-url"))

    assert statement.status == "failed"
    assert statement.parse_error == "Failed to download the statement file."
    assert "signed-url" not in statement.parse_error
    assert "SECRET" not in statement.parse_error


def test_parse_statement_corrupt_pdf(monkeypatch) -> None:
    statement = _make_statement("application/pdf")

    _run_task(monkeypatch, statement, b"this is not a real pdf file")

    assert statement.status == "failed"
    assert "corrupt" in statement.parse_error.lower()
