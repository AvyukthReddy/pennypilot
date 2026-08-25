from worker.confidence import compute_confidence
from worker.document_analysis import DocumentAnalysis
from worker.extracted_transactions import TransactionExtraction
from worker.financial_validation import (
    BalanceCheck,
    FinancialValidation,
    FinancialValidationIssue,
    RecoveryAttempt,
)
from worker.transaction_regions import TransactionRegion, TransactionRegionDetection
from worker.verification_issues import TransactionVerification


def _analysis(flagged_pages: list[int] | None = None) -> DocumentAnalysis:
    sections = [{"type": "transactions", "pages": flagged_pages}] if flagged_pages else []
    return DocumentAnalysis(document_type="bank_statement", sections=sections)


def _regions(*pages: int) -> TransactionRegionDetection:
    return TransactionRegionDetection(
        transaction_regions=[TransactionRegion(page=p, region=(0, 0, 100, 100)) for p in pages]
    )


def _extraction() -> TransactionExtraction:
    return TransactionExtraction(
        transactions=[
            {"transaction_date": "2026-07-14", "description": "Row", "amount": -5, "currency": "USD"},
        ],
    )


def test_perfect_statement_scores_1_and_validated() -> None:
    analysis = _analysis([1, 2])
    regions = _regions(1, 2)
    extraction_by_page = {1: _extraction(), 2: _extraction()}
    verification_by_page = {
        1: TransactionVerification(valid=True, issues=[]),
        2: TransactionVerification(valid=True, issues=[]),
    }

    result = compute_confidence(analysis, regions, extraction_by_page, verification_by_page, None)

    assert result.score == 1.0
    assert result.status == "validated"
    assert result.warnings == []
    assert result.breakdown.extraction == 1.0
    assert result.breakdown.verification == 1.0
    assert result.breakdown.financial_validation == 1.0
    assert result.breakdown.balance_reconciliation == 1.0
    assert result.breakdown.structural_consistency == 1.0


def test_no_document_analysis_treated_as_neutral() -> None:
    result = compute_confidence(None, None, {}, {}, None)

    assert result.score == 1.0
    assert result.status == "validated"
    assert result.warnings == []


def test_failed_extraction_for_a_region_lowers_extraction_component() -> None:
    analysis = _analysis([1, 2])
    regions = _regions(1, 2)
    extraction_by_page = {1: _extraction()}  # page 2 never extracted
    verification_by_page = {1: TransactionVerification(valid=True, issues=[])}

    result = compute_confidence(analysis, regions, extraction_by_page, verification_by_page, None)

    assert result.breakdown.extraction == 0.5
    assert any("page(s): 2" in w for w in result.warnings)


def test_uncorrected_verification_lowers_verification_component() -> None:
    analysis = _analysis([1, 2])
    regions = _regions(1, 2)
    extraction_by_page = {1: _extraction(), 2: _extraction()}
    verification_by_page = {
        1: TransactionVerification(valid=True, issues=[]),
        2: TransactionVerification(valid=False, issues=[]),
    }

    result = compute_confidence(analysis, regions, extraction_by_page, verification_by_page, None)

    assert result.breakdown.verification == 0.5
    assert any("page(s): 2" in w for w in result.warnings)


def test_missing_verification_record_counts_against_verification_component() -> None:
    analysis = _analysis([1])
    regions = _regions(1)
    extraction_by_page = {1: _extraction()}
    verification_by_page: dict = {}  # verification itself failed to run

    result = compute_confidence(analysis, regions, extraction_by_page, verification_by_page, None)

    assert result.breakdown.verification == 0.0


def test_non_balance_financial_issues_lower_that_component() -> None:
    fv = FinancialValidation(
        valid=False,
        issues=[
            FinancialValidationIssue(type="invalid_amount", description="zero amount"),
            FinancialValidationIssue(type="duplicate_transaction", description="2 duplicates"),
        ],
    )

    result = compute_confidence(None, None, {}, {}, fv)

    assert result.breakdown.financial_validation == 0.8  # 1 - 0.1*2
    assert "zero amount" in result.warnings
    assert "2 duplicates" in result.warnings


def test_balance_mismatch_issue_does_not_double_count_in_financial_component() -> None:
    fv = FinancialValidation(
        valid=False,
        issues=[FinancialValidationIssue(type="balance_mismatch", description="off by 50")],
        balance_check=BalanceCheck(
            beginning_balance="1000", net_change="-450", expected_ending_balance="550",
            actual_ending_balance="600", reconciled=False,
        ),
    )

    result = compute_confidence(None, None, {}, {}, fv)

    assert result.breakdown.financial_validation == 1.0  # balance_mismatch excluded here
    assert result.breakdown.balance_reconciliation == 0.0
    assert "Statement balance does not reconcile" in result.warnings


def test_reconciled_balance_with_no_recovery_is_full_credit() -> None:
    fv = FinancialValidation(
        valid=True,
        issues=[],
        balance_check=BalanceCheck(
            beginning_balance="1000", net_change="-50", expected_ending_balance="950",
            actual_ending_balance="950", reconciled=True,
        ),
    )

    result = compute_confidence(None, None, {}, {}, fv)

    assert result.breakdown.balance_reconciliation == 1.0


def test_reconciled_balance_only_via_recovery_gets_partial_credit() -> None:
    fv = FinancialValidation(
        valid=True,
        issues=[],
        balance_check=BalanceCheck(
            beginning_balance="1000", net_change="-50", expected_ending_balance="950",
            actual_ending_balance="950", reconciled=True,
        ),
        recovery_attempts=[RecoveryAttempt(page=1, succeeded=True)],
    )

    result = compute_confidence(None, None, {}, {}, fv)

    assert result.breakdown.balance_reconciliation == 0.8


def test_flagged_page_with_no_detected_region_lowers_structural_component() -> None:
    analysis = _analysis([1, 2, 3])
    regions = _regions(1, 2)  # page 3 flagged but never got a region

    result = compute_confidence(analysis, regions, {}, {}, None)

    assert result.breakdown.structural_consistency == 2 / 3
    assert any("no region detected" in w and w.endswith("3") for w in result.warnings)


def test_status_thresholds() -> None:
    # Force scores exactly at each boundary via financial-validation issue counts.
    perfect = compute_confidence(None, None, {}, {}, None)
    assert perfect.status == "validated"

    needs_review = compute_confidence(
        None, None, {}, {},
        FinancialValidation(
            valid=False,
            issues=[FinancialValidationIssue(type="invalid_amount", description="x")] * 4,
        ),
    )
    # financial component: 1 - 0.1*4 = 0.6 -> overall = 0.2*(1+1+0.6+1+1) = 0.92
    assert needs_review.score == 0.92
    assert needs_review.status == "validated"

    lower = compute_confidence(
        None, None, {}, {},
        FinancialValidation(
            valid=False,
            issues=[FinancialValidationIssue(type="invalid_amount", description="x")] * 9,
        ),
    )
    # financial component: max(0, 1 - 0.9) = 0.1 -> overall = 0.2*(1+1+0.1+1+1) = 0.82
    assert lower.score == 0.82
    assert lower.status == "needs_review"

    still_needs_review = compute_confidence(
        None, None, {}, {},
        FinancialValidation(
            valid=False,
            issues=[FinancialValidationIssue(type="invalid_amount", description="x")] * 10,
        ),
    )
    # financial component: max(0, 1 - 1.0) = 0.0 -> overall = 0.2*(1+1+0+1+1) = 0.8
    # still "needs_review" at 0.8 -- combine with a structural gap to push below 0.7.
    assert still_needs_review.score == 0.8
    assert still_needs_review.status == "needs_review"

    # extraction=1.0 (the one detected region was extracted), verification=1.0
    # (that region verified clean), financial=0.0 (10 issues),
    # balance=1.0 (no balance_check to fail), structural=1/3 (only 1 of 3
    # flagged pages got a detected region).
    # overall = 0.2*(1 + 1 + 0 + 1 + 1/3) = 0.6667 -> rounds to 0.667
    combined = compute_confidence(
        _analysis([1, 2, 3]),
        _regions(1),
        {1: _extraction()},
        {1: TransactionVerification(valid=True, issues=[])},
        FinancialValidation(
            valid=False,
            issues=[FinancialValidationIssue(type="invalid_amount", description="x")] * 10,
        ),
    )
    assert combined.score == 0.667
    assert combined.status == "unreliable"
