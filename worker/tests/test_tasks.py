import io
import uuid

import httpx
from reportlab.pdfgen import canvas

import worker.tasks as tasks
from worker.models import StatementRow


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


def test_parse_statement_scanned_pdf_flagged_not_failed(monkeypatch) -> None:
    statement = _make_statement("application/pdf")

    _run_task(monkeypatch, statement, _make_blank_pdf(pages=2))

    assert statement.status == "ingested"
    assert statement.page_count == 2
    assert statement.needs_ocr is True
    assert statement.parse_error is None
    assert len(statement.pages) == 2
    assert statement.pages[0]["text_blocks"] == []


def test_parse_statement_csv_happy_path(monkeypatch) -> None:
    statement = _make_statement("text/csv")
    csv_bytes = b"Date,Description,Amount\n07/14/2026,Coffee,-4.50\n"

    _run_task(monkeypatch, statement, csv_bytes)

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
