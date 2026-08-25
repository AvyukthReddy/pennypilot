from typing import Literal

from pydantic import BaseModel

from worker.document_analysis import DocumentAnalysis
from worker.extracted_transactions import TransactionExtraction
from worker.financial_validation import FinancialValidation
from worker.transaction_regions import TransactionRegionDetection
from worker.verification_issues import TransactionVerification

ConfidenceStatus = Literal["validated", "needs_review", "unreliable"]

# Each of the five signals contributes equally, a deliberate, transparent
# default, not reverse-engineered from any target number. Easy to retune
# later if one signal turns out to matter more in practice.
COMPONENT_WEIGHT = 0.2

VALIDATED_THRESHOLD = 0.9
NEEDS_REVIEW_THRESHOLD = 0.7

# Reconciled only after Phase 9 recovery kicked in: correct, but needed
# help, so not quite full credit.
RECOVERED_BALANCE_SCORE = 0.8

# Each non-balance financial-validation issue costs this much off the
# component score (floored at 0), rather than any single issue tanking it.
FINANCIAL_ISSUE_PENALTY = 0.1


class ConfidenceBreakdown(BaseModel):
    extraction: float
    verification: float
    financial_validation: float
    balance_reconciliation: float
    structural_consistency: float


class Confidence(BaseModel):
    score: float
    status: ConfidenceStatus
    warnings: list[str] = []
    breakdown: ConfidenceBreakdown


def _extraction_score(
    transaction_regions: TransactionRegionDetection | None,
    extraction_by_page: dict[int, TransactionExtraction],
) -> tuple[float, list[str]]:
    total = len(transaction_regions.transaction_regions) if transaction_regions else 0
    if total == 0:
        return 1.0, []
    extracted = len(extraction_by_page)
    warnings: list[str] = []
    if extracted < total:
        missing = sorted(
            region.page
            for region in transaction_regions.transaction_regions
            if region.page not in extraction_by_page
        )
        warnings.append(
            f"Extraction failed entirely for page(s): {', '.join(map(str, missing))}"
        )
    return extracted / total, warnings


def _verification_score(
    extraction_by_page: dict[int, TransactionExtraction],
    verification_by_page: dict[int, TransactionVerification],
) -> tuple[float, list[str]]:
    total = len(extraction_by_page)
    if total == 0:
        return 1.0, []
    clean_pages = [
        page
        for page in extraction_by_page
        if verification_by_page.get(page) is not None and verification_by_page[page].valid
    ]
    warnings: list[str] = []
    if len(clean_pages) < total:
        flagged = sorted(page for page in extraction_by_page if page not in clean_pages)
        warnings.append(
            f"Verification flagged or was unavailable for page(s): "
            f"{', '.join(map(str, flagged))}"
        )
    return len(clean_pages) / total, warnings


def _financial_validation_score(
    financial_validation: FinancialValidation | None,
) -> tuple[float, list[str]]:
    if financial_validation is None:
        return 1.0, []
    non_balance_issues = [
        issue for issue in financial_validation.issues if issue.type != "balance_mismatch"
    ]
    if not non_balance_issues:
        return 1.0, []
    score = max(0.0, 1.0 - FINANCIAL_ISSUE_PENALTY * len(non_balance_issues))
    return score, [issue.description for issue in non_balance_issues]


def _balance_score(
    financial_validation: FinancialValidation | None,
) -> tuple[float, list[str]]:
    if financial_validation is None or financial_validation.balance_check is None:
        return 1.0, []
    if not financial_validation.balance_check.reconciled:
        return 0.0, ["Statement balance does not reconcile"]
    if financial_validation.recovery_attempts:
        return RECOVERED_BALANCE_SCORE, []
    return 1.0, []


def _structural_consistency_score(
    document_analysis: DocumentAnalysis | None,
    transaction_regions: TransactionRegionDetection | None,
) -> tuple[float, list[str]]:
    if document_analysis is None:
        return 1.0, []
    flagged_pages = {
        page
        for section in document_analysis.sections
        if section.type == "transactions"
        for page in section.pages
    }
    if not flagged_pages:
        return 1.0, []
    region_pages = (
        {region.page for region in transaction_regions.transaction_regions}
        if transaction_regions
        else set()
    )
    missing = sorted(flagged_pages - region_pages)
    warnings: list[str] = []
    if missing:
        warnings.append(
            f"Page(s) flagged as transactions but no region detected: "
            f"{', '.join(map(str, missing))}"
        )
    return len(flagged_pages & region_pages) / len(flagged_pages), warnings


def compute_confidence(
    document_analysis: DocumentAnalysis | None,
    transaction_regions: TransactionRegionDetection | None,
    extraction_by_page: dict[int, TransactionExtraction],
    verification_by_page: dict[int, TransactionVerification],
    financial_validation: FinancialValidation | None,
) -> Confidence:
    """Deterministic, non-AI composite confidence score for a statement's
    extracted transactions. Combines extraction completeness, verification
    cleanliness, financial-validation issue count, balance reconciliation
    (including whether Phase 9 recovery was needed), and structural
    consistency (did every page flagged as "transactions" actually get a
    detected region). Not an LLM self-report of confidence; every input is
    a signal this pipeline already computed."""
    extraction, extraction_warnings = _extraction_score(transaction_regions, extraction_by_page)
    verification, verification_warnings = _verification_score(
        extraction_by_page, verification_by_page
    )
    financial, financial_warnings = _financial_validation_score(financial_validation)
    balance, balance_warnings = _balance_score(financial_validation)
    structural, structural_warnings = _structural_consistency_score(
        document_analysis, transaction_regions
    )

    score = round(
        COMPONENT_WEIGHT * (extraction + verification + financial + balance + structural), 3
    )
    if score >= VALIDATED_THRESHOLD:
        status: ConfidenceStatus = "validated"
    elif score >= NEEDS_REVIEW_THRESHOLD:
        status = "needs_review"
    else:
        status = "unreliable"

    return Confidence(
        score=score,
        status=status,
        warnings=(
            extraction_warnings
            + verification_warnings
            + financial_warnings
            + balance_warnings
            + structural_warnings
        ),
        breakdown=ConfidenceBreakdown(
            extraction=extraction,
            verification=verification,
            financial_validation=financial,
            balance_reconciliation=balance,
            structural_consistency=structural,
        ),
    )
