from worker.document import Document, Page
from worker.extracted_transactions import TransactionExtraction
from worker.financial_validation import FinancialValidation, FinancialValidationIssue
from worker.recovery import attempt_recovery
from worker.transaction_regions import TransactionRegion, TransactionRegionDetection
from worker.transaction_schema import TransactionFields
from worker.verification_issues import TransactionVerification


class _FakeExtractionService:
    """Stand-in for TransactionExtractionService, no real network call.
    `results_by_page` (page -> TransactionExtraction | Exception) drives
    what a recovery attempt on that page produces."""

    def __init__(self, results_by_page: dict, calls: list) -> None:
        self._results_by_page = results_by_page
        self._calls = calls

    def extract(
        self,
        document,
        region,
        transaction_fields,
        statement_period=None,
        previous_attempt=None,
        recovery_hint=None,
    ):
        self._calls.append(region.page)
        outcome = self._results_by_page.get(region.page)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            raise AssertionError(f"no fake result configured for page {region.page}")
        return outcome


def _document() -> Document:
    return Document(
        statement_id="stmt-1",
        filename="statement.pdf",
        content_type="application/pdf",
        data=b"",
        file_hash="hash",
        size_bytes=0,
        page_count=3,
        parser_version="2",
        pages=[Page(page_number=n, width=612, height=792, text="", text_blocks=[], images=[]) for n in (1, 2, 3)],
        needs_ocr=False,
    )


def _regions(*pages: int) -> TransactionRegionDetection:
    return TransactionRegionDetection(
        transaction_regions=[TransactionRegion(page=p, region=(0, 0, 100, 100)) for p in pages]
    )


def _fields() -> TransactionFields:
    return TransactionFields(
        transaction_date={"source": "column_1"},
        description={"source": "column_2"},
        amount=[{"source": "column_3"}],
    )


def _extraction(amount: str) -> TransactionExtraction:
    return TransactionExtraction(
        transactions=[
            {"transaction_date": "2026-07-14", "description": "Row", "amount": amount, "currency": "USD"},
        ],
    )


MISMATCH_VALIDATION = FinancialValidation(
    valid=False,
    issues=[FinancialValidationIssue(type="balance_mismatch", description="off by 50.00")],
)

VALID_VALIDATION = FinancialValidation(valid=True, issues=[])

NON_BALANCE_VALIDATION = FinancialValidation(
    valid=False,
    issues=[FinancialValidationIssue(type="duplicate_transaction", description="2 duplicates")],
)


def _make_validate(reconciles_with_page: int):
    """A fake `validate` callback: reconciles only once the candidate dict
    contains an extraction for `reconciles_with_page`."""

    def validate(candidate: dict) -> FinancialValidation:
        if reconciles_with_page in candidate:
            return VALID_VALIDATION
        return MISMATCH_VALIDATION

    return validate


def test_noop_when_already_valid() -> None:
    calls: list = []
    extraction_by_page = {1: _extraction("-7.42")}

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1), _fields(), extraction_by_page, {}, VALID_VALIDATION,
        validate=lambda c: VALID_VALIDATION,
        extraction_service=_FakeExtractionService({}, calls),
    )

    assert result_by_page is extraction_by_page
    assert result_validation is VALID_VALIDATION
    assert calls == []


def test_noop_when_no_balance_mismatch_issue() -> None:
    calls: list = []
    extraction_by_page = {1: _extraction("-7.42")}

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1), _fields(), extraction_by_page, {}, NON_BALANCE_VALIDATION,
        validate=lambda c: NON_BALANCE_VALIDATION,
        extraction_service=_FakeExtractionService({}, calls),
    )

    assert result_by_page is extraction_by_page
    assert result_validation is NON_BALANCE_VALIDATION
    assert calls == []


def test_suspect_pages_tried_before_clean_ones() -> None:
    calls: list = []
    extraction_by_page = {1: _extraction("-7.42"), 2: _extraction("-5.00")}
    verification_by_page = {
        1: TransactionVerification(valid=True, issues=[]),  # clean
        # page 2 has no verification entry at all -> suspect
    }
    fake = _FakeExtractionService({2: _extraction("-55.00")}, calls)

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1, 2), _fields(), extraction_by_page, verification_by_page,
        MISMATCH_VALIDATION, validate=_make_validate(reconciles_with_page=2),
        extraction_service=fake,
    )

    assert calls == [2]  # suspect page tried first, and it succeeded, so page 1 never tried
    assert result_validation.valid is True
    assert [a.page for a in result_validation.recovery_attempts] == [2]
    assert result_validation.recovery_attempts[0].succeeded is True
    assert result_by_page[2] == _extraction("-55.00")


def test_stops_on_first_reconciled_candidate() -> None:
    calls: list = []
    extraction_by_page = {1: _extraction("-7.42"), 2: _extraction("-5.00")}
    fake = _FakeExtractionService(
        {1: _extraction("-52.42"), 2: _extraction("-55.00")}, calls
    )

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1, 2), _fields(), extraction_by_page, {},
        MISMATCH_VALIDATION, validate=_make_validate(reconciles_with_page=1),
        extraction_service=fake,
    )

    assert calls == [1]
    assert result_validation.valid is True
    assert result_by_page[1] == _extraction("-52.42")
    assert result_by_page[2] == _extraction("-5.00")  # untouched


def test_gives_up_after_trying_every_candidate() -> None:
    calls: list = []
    extraction_by_page = {1: _extraction("-7.42"), 2: _extraction("-5.00")}
    fake = _FakeExtractionService(
        {1: _extraction("-1.00"), 2: _extraction("-2.00")}, calls
    )

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1, 2), _fields(), extraction_by_page, {},
        MISMATCH_VALIDATION, validate=lambda c: MISMATCH_VALIDATION,
        extraction_service=fake,
    )

    assert sorted(calls) == [1, 2]
    assert result_validation.valid is False
    assert len(result_validation.recovery_attempts) == 2
    assert all(not attempt.succeeded for attempt in result_validation.recovery_attempts)
    assert result_by_page is extraction_by_page  # nothing reconciled, original kept


def test_extraction_failure_for_one_candidate_tries_the_next() -> None:
    calls: list = []
    extraction_by_page = {1: _extraction("-7.42"), 2: _extraction("-5.00")}
    fake = _FakeExtractionService(
        {1: RuntimeError("model unreachable"), 2: _extraction("-55.00")}, calls
    )

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1, 2), _fields(), extraction_by_page, {},
        MISMATCH_VALIDATION, validate=_make_validate(reconciles_with_page=2),
        extraction_service=fake,
    )

    assert calls == [1, 2]
    assert result_validation.valid is True
    assert [a.page for a in result_validation.recovery_attempts] == [1, 2]
    assert result_validation.recovery_attempts[0].succeeded is False
    assert result_validation.recovery_attempts[1].succeeded is True


def test_validate_failure_for_one_candidate_tries_the_next() -> None:
    calls: list = []
    extraction_by_page = {1: _extraction("-7.42"), 2: _extraction("-5.00")}
    fake = _FakeExtractionService(
        {1: _extraction("-1.00"), 2: _extraction("-55.00")}, calls
    )
    validate_calls: list = []

    def validate(candidate: dict) -> FinancialValidation:
        validate_calls.append(candidate)
        if len(validate_calls) == 1:
            raise RuntimeError("boom")
        return _make_validate(reconciles_with_page=2)(candidate)

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1, 2), _fields(), extraction_by_page, {},
        MISMATCH_VALIDATION, validate=validate,
        extraction_service=fake,
    )

    assert calls == [1, 2]
    assert result_validation.valid is True


def test_candidate_with_no_prior_extraction_is_still_tried() -> None:
    calls: list = []
    # Page 2 was never successfully extracted originally (e.g. it raised).
    extraction_by_page = {1: _extraction("-7.42")}
    fake = _FakeExtractionService({2: _extraction("-55.00")}, calls)

    result_by_page, result_validation = attempt_recovery(
        _document(), _regions(1, 2), _fields(), extraction_by_page, {},
        MISMATCH_VALIDATION, validate=_make_validate(reconciles_with_page=2),
        extraction_service=fake,
    )

    assert 2 in calls
    assert result_validation.valid is True
    assert result_by_page[2] == _extraction("-55.00")
