import io
import uuid
from decimal import Decimal

import httpx
import pytest
from reportlab.pdfgen import canvas

import worker.tasks as tasks
from worker.document_analysis import DocumentAnalysis
from worker.extracted_transactions import TransactionExtraction
from worker.models import StatementRow
from worker.transaction_regions import TransactionRegionDetection
from worker.transaction_schema import TransactionSchemaDiscovery
from worker.verification_issues import TransactionVerification

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

EMPTY_REGIONS = TransactionRegionDetection(transaction_regions=[])

VALID_SCHEMA = TransactionSchemaDiscovery(
    transaction_fields={
        "transaction_date": {"source": "column_1"},
        "description": {"source": "column_2"},
        "amount": [{"source": "column_3"}],
    },
)

VALID_EXTRACTION = TransactionExtraction(
    transactions=[
        {
            "transaction_date": "2026-07-14",
            "description": "STARBUCKS #2938",
            "amount": -7.42,
            "currency": "USD",
        },
    ],
)

EMPTY_EXTRACTION = TransactionExtraction(transactions=[])

VALID_VERIFICATION = TransactionVerification(valid=True, issues=[])

CORRECTED_EXTRACTION = TransactionExtraction(
    transactions=[
        {
            "transaction_date": "2026-07-14",
            "description": "STARBUCKS #2938",
            "amount": -7.50,
            "currency": "USD",
        },
    ],
)

INVALID_VERIFICATION = TransactionVerification(
    valid=False,
    issues=[{"type": "wrong_amount", "page": 1, "description": "amount should be -7.50"}],
)

ANALYSIS_WITH_BALANCE = DocumentAnalysis(
    document_type="bank_statement",
    currency="USD",
    sections=[{"type": "transactions", "pages": [1]}],
    beginning_balance=Decimal("1000"),
    ending_balance=Decimal("992.58"),
)

# 1000 - 7.42 = 992.58 (matches VALID_EXTRACTION), but the statement's
# actual ending balance is 977.16, so the initial extraction is short by
# a second, missed transaction. Recovery should catch this.
ANALYSIS_FOR_RECOVERY = DocumentAnalysis(
    document_type="bank_statement",
    currency="USD",
    sections=[{"type": "transactions", "pages": [1]}],
    beginning_balance=Decimal("1000"),
    ending_balance=Decimal("977.16"),
)

RECOVERED_EXTRACTION = TransactionExtraction(
    transactions=[
        {
            "transaction_date": "2026-07-14",
            "description": "STARBUCKS #2938",
            "amount": -7.42,
            "currency": "USD",
        },
        {
            "transaction_date": "2026-07-18",
            "description": "UBER TRIP",
            "amount": -15.42,
            "currency": "USD",
        },
    ],
)


class _FakeUnderstandingService:
    """Stand-in for DocumentUnderstandingService, no real network call.
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


def _spy_on_set_stage(monkeypatch) -> list[tuple[str, str | None]]:
    """Records every (stage, detail) pair tasks._set_stage is called with,
    while still performing its real side effects (setting stmt.processing_*
    and committing) so downstream code sees correct state. More reliable
    than inferring stages from FakeTaskSession.commit() call sites, since
    plain status-only commits elsewhere in parse_statement would otherwise
    get misread as stage transitions too."""
    calls: list[tuple[str, str | None]] = []
    original = tasks._set_stage

    def _spy(session, stmt, stage, detail=None):
        calls.append((stage, detail))
        original(session, stmt, stage, detail)

    monkeypatch.setattr(tasks, "_set_stage", _spy)
    return calls


class _FakeRegionDetectionService:
    """Stand-in for TransactionRegionDetectionService, no real network call."""

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


class _FakeSchemaDiscoveryService:
    """Stand-in for TransactionSchemaDiscoveryService, no real network call."""

    def __init__(
        self,
        calls: list,
        result: TransactionSchemaDiscovery | None = None,
        error: Exception | None = None,
    ):
        self._calls = calls
        self._result = result
        self._error = error

    def discover(self, document, transaction_regions):
        self._calls.append((document, transaction_regions))
        if self._error:
            raise self._error
        return self._result


def _patch_schema_discovery(monkeypatch, result=None, error=None):
    calls: list = []
    monkeypatch.setattr(
        tasks,
        "TransactionSchemaDiscoveryService",
        lambda: _FakeSchemaDiscoveryService(calls, result=result, error=error),
    )
    return calls


class _FakeExtractionService:
    """Stand-in for TransactionExtractionService, no real network call.
    `results_by_page` lets a test vary the outcome per region (e.g. one page
    succeeds, another raises), falling back to a single `result`/`error` for
    every region when not given. `retry_results_by_page` is consulted
    instead whenever `previous_attempt` is set, i.e. this is the corrective
    re-extraction call, not the original one."""

    def __init__(
        self,
        calls: list,
        result: TransactionExtraction | None = None,
        error: Exception | None = None,
        results_by_page: dict | None = None,
        retry_results_by_page: dict | None = None,
        recovery_results_by_page: dict | None = None,
    ):
        self._calls = calls
        self._result = result
        self._error = error
        self._results_by_page = results_by_page or {}
        self._retry_results_by_page = retry_results_by_page or {}
        self._recovery_results_by_page = recovery_results_by_page or {}

    def extract(
        self,
        document,
        region,
        transaction_fields,
        statement_period=None,
        previous_attempt=None,
        verification_issues=None,
        recovery_hint=None,
    ):
        self._calls.append(
            (document, region, transaction_fields, previous_attempt, verification_issues, recovery_hint)
        )
        if recovery_hint is not None and region.page in self._recovery_results_by_page:
            outcome = self._recovery_results_by_page[region.page]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if previous_attempt is not None and region.page in self._retry_results_by_page:
            outcome = self._retry_results_by_page[region.page]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if region.page in self._results_by_page:
            outcome = self._results_by_page[region.page]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if self._error:
            raise self._error
        return self._result


def _patch_extraction(
    monkeypatch,
    result=None,
    error=None,
    results_by_page=None,
    retry_results_by_page=None,
    recovery_results_by_page=None,
):
    calls: list = []
    monkeypatch.setattr(
        tasks,
        "TransactionExtractionService",
        lambda: _FakeExtractionService(
            calls,
            result=result,
            error=error,
            results_by_page=results_by_page,
            retry_results_by_page=retry_results_by_page,
            recovery_results_by_page=recovery_results_by_page,
        ),
    )
    return calls


class _FakeVerificationService:
    """Stand-in for TransactionVerificationService, no real network call."""

    def __init__(
        self,
        calls: list,
        result: TransactionVerification | None = None,
        error: Exception | None = None,
        results_by_page: dict | None = None,
    ):
        self._calls = calls
        self._result = result
        self._error = error
        self._results_by_page = results_by_page or {}

    def verify(self, document, region, extraction):
        self._calls.append((document, region, extraction))
        if region.page in self._results_by_page:
            outcome = self._results_by_page[region.page]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if self._error:
            raise self._error
        return self._result


def _patch_verification(monkeypatch, result=None, error=None, results_by_page=None):
    calls: list = []
    monkeypatch.setattr(
        tasks,
        "TransactionVerificationService",
        lambda: _FakeVerificationService(calls, result=result, error=error, results_by_page=results_by_page),
    )
    return calls


class FakeTaskSession:
    def __init__(self, statement: StatementRow) -> None:
        self.statement = statement
        self.rolled_back = False
        self.added: list = []

    def get(self, model, pk):
        if model is StatementRow and pk == self.statement.id:
            return self.statement
        return None

    def add_all(self, rows) -> None:
        self.added.extend(rows)

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
    schema_calls = _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    extraction_calls = _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    verification_calls = _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

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
    # Real page images are rendered during analyze_pdf, but never persisted.
    assert "image" not in first_page

    assert len(calls) == 1
    assert statement.document_analysis["document_type"] == "bank_statement"
    assert statement.document_analysis["institution"] == "Chase"

    assert len(region_calls) == 1
    assert statement.transaction_regions["transaction_regions"][0]["page"] == 1

    assert len(schema_calls) == 1
    assert (
        statement.transaction_schema["transaction_fields"]["transaction_date"]["source"]
        == "column_1"
    )

    assert len(extraction_calls) == 1
    assert len(session.added) == 1
    row = session.added[0]
    assert row.statement_id == statement.id
    assert row.user_id == statement.user_id
    assert row.description == "STARBUCKS #2938"
    assert row.amount == Decimal("-7.42")
    assert row.currency == "USD"

    assert len(verification_calls) == 1
    # No retry, extraction was only called once for the region.
    assert len(extraction_calls) == 1
    assert statement.transaction_verification == {"valid": True, "issues": []}

    # Financial validation is real (not mocked), pure Python, no provider.
    assert statement.financial_validation == {
        "valid": True,
        "issues": [],
        "balance_check": None,
        "recovery_attempts": [],
    }

    # Confidence is real (not mocked): pure Python, combines everything above.
    confidence = statement.confidence
    assert confidence["score"] == 1.0
    assert confidence["status"] == "validated"
    assert confidence["warnings"] == []


def test_parse_statement_processing_stage_progression_happy_path(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    stage_calls = _spy_on_set_stage(monkeypatch)
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    # "ingesting" is folded into the initial status="processing" commit, not
    # via _set_stage, so it isn't captured here; statement.processing_stage
    # (checked below) confirms it was still set correctly.
    assert [stage for stage, _ in stage_calls] == [
        "understanding",
        "detecting_regions",
        "discovering_schema",
        "extracting",  # before the (single-region) loop, detail=None
        "extracting",  # first (only) region
        "validating",
        "scoring_confidence",
    ]
    assert statement.processing_stage == "scoring_confidence"
    assert statement.processing_detail is None


def test_parse_statement_processing_detail_tracks_current_region(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    stage_calls = _spy_on_set_stage(monkeypatch)
    two_regions = TransactionRegionDetection(
        transaction_regions=[
            {"page": 1, "region": [45, 180, 570, 730]},
            {"page": 2, "region": [45, 180, 570, 730]},
        ],
    )
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=two_regions)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    extracting_details = [detail for stage, detail in stage_calls if stage == "extracting"]
    assert extracting_details == [None, "Region 1 of 2", "Region 2 of 2"]


def test_parse_statement_processing_stage_reached_despite_downstream_failure(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    stage_calls = _spy_on_set_stage(monkeypatch)
    _patch_understanding(monkeypatch, error=RuntimeError("model unreachable"))

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    # The "understanding" guard passed (real PDF, not scanned), so its stage
    # marker was committed before the call itself raised.
    assert statement.processing_stage == "understanding"
    assert [stage for stage, _ in stage_calls] == ["understanding"]


def test_parse_statement_processing_stage_skips_region_detection_without_transactions_section(
    monkeypatch,
) -> None:
    statement = _make_statement("application/pdf")
    stage_calls = _spy_on_set_stage(monkeypatch)
    _patch_understanding(monkeypatch, result=ANALYSIS_WITHOUT_TRANSACTIONS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    # Neither detecting_regions nor scoring_confidence's guard (same
    # "has a transactions section" condition) ever passes.
    assert [stage for stage, _ in stage_calls] == ["understanding"]
    assert statement.processing_stage == "understanding"


def test_parse_statement_processing_stage_jumps_to_confidence_when_region_detection_fails(
    monkeypatch,
) -> None:
    statement = _make_statement("application/pdf")
    stage_calls = _spy_on_set_stage(monkeypatch)
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, error=RuntimeError("model unreachable"))

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    # discovering_schema/extracting/validating never get their own stage
    # commits since transaction_regions stays None, but scoring_confidence's
    # guard is independent (based on document_analysis, not
    # transaction_regions), so it still fires right after. Documented v1
    # behavior: the stepper "jumps forward" over stages that never ran.
    assert [stage for stage, _ in stage_calls] == [
        "understanding",
        "detecting_regions",
        "scoring_confidence",
    ]


def test_parse_statement_processing_stage_reflects_last_reached_on_hard_failure(
    monkeypatch,
) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = FakeTaskSession(statement)

    def _failing_add_all(rows) -> None:
        raise RuntimeError("boom")

    session.add_all = _failing_add_all
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    def _fake_get(url, timeout=60):
        return httpx.Response(
            200, content=_make_pdf(pages=3), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(tasks.httpx, "get", _fake_get)

    with pytest.raises(RuntimeError):
        tasks.parse_statement(str(statement.id), "https://example.com/signed?token=SECRET")

    # session.add_all (right before the final commit) isn't wrapped in any
    # per-phase try/except, so this reaches the outer handler. status flips
    # to "failed", but processing_stage is left at the last phase actually
    # reached (every phase ran and committed its own stage marker before
    # add_all was ever called) rather than reset.
    assert statement.status == "failed"
    assert statement.processing_stage == "scoring_confidence"


def test_parse_statement_document_understanding_failure_is_non_fatal(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, error=RuntimeError("model unreachable"))

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.document_analysis is None
    # No document_analysis at all ⇒ region detection is never even reached.
    assert statement.transaction_regions is None
    assert statement.transaction_schema is None
    # No transactions section to score ⇒ confidence is never computed.
    assert statement.confidence is None


def test_parse_statement_region_detection_failure_is_non_fatal(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, error=RuntimeError("model unreachable"))

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.document_analysis is not None
    assert statement.transaction_regions is None
    # No transaction_regions at all ⇒ schema discovery is never reached.
    assert statement.transaction_schema is None


def test_parse_statement_skips_region_detection_without_transactions_section(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=ANALYSIS_WITHOUT_TRANSACTIONS)
    region_calls = _patch_region_detection(monkeypatch, result=VALID_REGIONS)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.document_analysis is not None
    assert region_calls == []
    assert statement.transaction_regions is None
    assert statement.transaction_schema is None
    # document_analysis exists but flags no "transactions" section ⇒ still
    # nothing to score.
    assert statement.confidence is None


def test_parse_statement_schema_discovery_failure_is_non_fatal(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, error=RuntimeError("model unreachable"))
    extraction_calls = _patch_extraction(monkeypatch, result=VALID_EXTRACTION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.transaction_regions is not None
    assert statement.transaction_schema is None
    # No transaction_schema at all ⇒ extraction is never reached.
    assert extraction_calls == []
    assert session.added == []


def test_parse_statement_skips_schema_discovery_without_regions(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=EMPTY_REGIONS)
    schema_calls = _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.transaction_regions == {"transaction_regions": []}
    assert schema_calls == []
    assert statement.transaction_schema is None


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
    # Scanned/no-text documents skip understanding entirely, no point
    # classifying a document with nothing extracted from it.
    assert calls == []
    assert statement.document_analysis is None
    assert statement.transaction_regions is None
    assert statement.transaction_schema is None


def test_parse_statement_csv_happy_path(monkeypatch) -> None:
    statement = _make_statement("text/csv")
    csv_bytes = b"Date,Description,Amount\n07/14/2026,Coffee,-4.50\n"
    calls = _patch_understanding(monkeypatch, result=VALID_ANALYSIS)

    _run_task(monkeypatch, statement, csv_bytes)

    assert calls == []
    assert statement.document_analysis is None
    assert statement.transaction_regions is None
    assert statement.transaction_schema is None
    assert statement.status == "ingested"
    assert statement.page_count is None
    assert statement.parser_version == tasks.INGESTION_VERSION
    assert statement.needs_ocr is False
    assert statement.pages == []


def test_parse_statement_extraction_partial_failure_keeps_other_regions(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    two_regions = TransactionRegionDetection(
        transaction_regions=[
            {"page": 1, "region": [45, 180, 570, 730]},
            {"page": 2, "region": [45, 180, 570, 730]},
        ],
    )
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=two_regions)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    extraction_calls = _patch_extraction(
        monkeypatch,
        results_by_page={1: RuntimeError("model unreachable"), 2: VALID_EXTRACTION},
    )
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert len(extraction_calls) == 2
    # Page 1's failure doesn't discard page 2's already-extracted transaction.
    assert len(session.added) == 1
    assert session.added[0].description == "STARBUCKS #2938"


def test_parse_statement_extraction_currency_falls_back_to_document_analysis(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    no_currency_extraction = TransactionExtraction(
        transactions=[
            {
                "transaction_date": "2026-07-14",
                "description": "STARBUCKS #2938",
                "amount": -7.42,
                "currency": None,
            },
        ],
    )
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    _patch_extraction(monkeypatch, result=no_currency_extraction)
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert len(session.added) == 1
    assert session.added[0].currency == VALID_ANALYSIS.currency == "USD"


def test_parse_statement_financial_validation_reconciles_balance(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=ANALYSIS_WITH_BALANCE)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    validation = statement.financial_validation
    assert validation["valid"] is True
    assert validation["balance_check"]["reconciled"] is True
    assert validation["balance_check"]["expected_ending_balance"] == "992.58"


def test_parse_statement_financial_validation_detects_duplicate_across_regions(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    two_regions = TransactionRegionDetection(
        transaction_regions=[
            {"page": 1, "region": [45, 180, 570, 730]},
            {"page": 2, "region": [45, 180, 570, 730]},
        ],
    )
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=two_regions)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    # Both regions independently "find" the exact same transaction, a
    # realistic failure mode when adjacent regions overlap near a page break.
    _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert len(session.added) == 2
    validation = statement.financial_validation
    assert validation["valid"] is False
    assert any(issue["type"] == "duplicate_transaction" for issue in validation["issues"])


def test_parse_statement_skips_financial_validation_without_transactions(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=EMPTY_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)

    _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert statement.financial_validation is None


def test_parse_statement_recovery_fixes_balance_mismatch(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=ANALYSIS_FOR_RECOVERY)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    extraction_calls = _patch_extraction(
        monkeypatch,
        results_by_page={1: VALID_EXTRACTION},
        recovery_results_by_page={1: RECOVERED_EXTRACTION},
    )
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    # Original extraction, then one recovery re-extraction for the same page.
    assert len(extraction_calls) == 2
    assert extraction_calls[1][5] is not None  # recovery_hint set on the recovery call
    assert len(session.added) == 2
    assert {row.description for row in session.added} == {"STARBUCKS #2938", "UBER TRIP"}
    validation = statement.financial_validation
    assert validation["valid"] is True
    assert validation["recovery_attempts"] == [{"page": 1, "succeeded": True}]


def test_parse_statement_recovery_gives_up_when_unresolved(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=ANALYSIS_FOR_RECOVERY)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    extraction_calls = _patch_extraction(
        monkeypatch,
        results_by_page={1: VALID_EXTRACTION},
        recovery_results_by_page={1: VALID_EXTRACTION},  # re-extraction reproduces the same gap
    )
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert len(extraction_calls) == 2
    validation = statement.financial_validation
    assert validation["valid"] is False
    assert validation["recovery_attempts"] == [{"page": 1, "succeeded": False}]
    # Recovery didn't help, so the original (pre-recovery) rows are kept.
    assert len(session.added) == 1
    assert session.added[0].description == "STARBUCKS #2938"


def test_parse_statement_recovery_not_attempted_without_balance_mismatch(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    two_regions = TransactionRegionDetection(
        transaction_regions=[
            {"page": 1, "region": [45, 180, 570, 730]},
            {"page": 2, "region": [45, 180, 570, 730]},
        ],
    )
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)  # no beginning/ending balance
    _patch_region_detection(monkeypatch, result=two_regions)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    # Both regions "find" the exact same transaction -> duplicate, not a balance issue.
    extraction_calls = _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    _patch_verification(monkeypatch, result=VALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    # One extraction call per region, no recovery calls on top.
    assert len(extraction_calls) == 2
    assert len(session.added) == 2
    validation = statement.financial_validation
    assert validation["valid"] is False
    assert any(issue["type"] == "duplicate_transaction" for issue in validation["issues"])
    assert validation["recovery_attempts"] == []


def test_parse_statement_invalid_verification_triggers_corrective_retry(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    extraction_calls = _patch_extraction(
        monkeypatch,
        results_by_page={1: VALID_EXTRACTION},
        retry_results_by_page={1: CORRECTED_EXTRACTION},
    )
    verification_calls = _patch_verification(monkeypatch, result=INVALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert len(verification_calls) == 1
    # Original call + one corrective retry.
    assert len(extraction_calls) == 2
    assert extraction_calls[0][3] is None  # previous_attempt on the original call
    assert extraction_calls[1][3] == VALID_EXTRACTION  # previous_attempt on the retry
    assert extraction_calls[1][4] == INVALID_VERIFICATION.issues
    # Persisted rows come from the retry's corrected output.
    assert len(session.added) == 1
    assert session.added[0].amount == Decimal("-7.50")
    # The persisted report reflects the *first* (invalid) verification.
    assert statement.transaction_verification["valid"] is False
    assert len(statement.transaction_verification["issues"]) == 1
    assert statement.transaction_verification["issues"][0]["type"] == "wrong_amount"


def test_parse_statement_verification_failure_is_non_fatal(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    extraction_calls = _patch_extraction(monkeypatch, result=VALID_EXTRACTION)
    _patch_verification(monkeypatch, error=RuntimeError("model unreachable"))

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    # No verdict at all ⇒ no retry attempted, original extraction kept.
    assert len(extraction_calls) == 1
    assert len(session.added) == 1
    assert session.added[0].description == "STARBUCKS #2938"
    assert statement.transaction_verification is None


def test_parse_statement_corrective_retry_failure_keeps_original_extraction(monkeypatch) -> None:
    statement = _make_statement("application/pdf")
    _patch_understanding(monkeypatch, result=VALID_ANALYSIS)
    _patch_region_detection(monkeypatch, result=VALID_REGIONS)
    _patch_schema_discovery(monkeypatch, result=VALID_SCHEMA)
    extraction_calls = _patch_extraction(
        monkeypatch,
        results_by_page={1: VALID_EXTRACTION},
        retry_results_by_page={1: RuntimeError("model unreachable")},
    )
    _patch_verification(monkeypatch, result=INVALID_VERIFICATION)

    session = _run_task(monkeypatch, statement, _make_pdf(pages=3))

    assert statement.status == "ingested"
    assert len(extraction_calls) == 2
    # The retry failed, so the pre-retry (original) extraction is persisted.
    assert len(session.added) == 1
    assert session.added[0].amount == Decimal("-7.42")
    assert statement.transaction_verification["valid"] is False


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
