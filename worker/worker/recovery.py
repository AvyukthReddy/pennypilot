import logging
from typing import Callable

from worker.document import Document
from worker.extracted_transactions import TransactionExtraction
from worker.financial_validation import FinancialValidation, RecoveryAttempt
from worker.transaction_extraction import TransactionExtractionService
from worker.transaction_regions import TransactionRegionDetection
from worker.transaction_schema import TransactionFields
from worker.verification_issues import TransactionVerification

logger = logging.getLogger(__name__)


def attempt_recovery(
    document: Document,
    transaction_regions: TransactionRegionDetection,
    transaction_fields: TransactionFields,
    extraction_by_page: dict[int, TransactionExtraction],
    verification_by_page: dict[int, TransactionVerification],
    financial_validation: FinancialValidation,
    validate: Callable[[dict[int, TransactionExtraction]], FinancialValidation],
    extraction_service: TransactionExtractionService | None = None,
) -> tuple[dict[int, TransactionExtraction], FinancialValidation]:
    """When `financial_validation` failed with a balance_mismatch, tries
    re-extracting one region at a time (suspect regions, no successful
    Phase-7 verification, first, then the rest in page order) and
    re-validating after each, stopping as soon as one reconciles. Returns
    the (possibly updated) extraction_by_page and the final
    FinancialValidation, whose recovery_attempts records every candidate
    tried. A no-op, returns the inputs unchanged, when validation already
    passed or the failure isn't a balance_mismatch."""
    if financial_validation.valid:
        return extraction_by_page, financial_validation

    mismatch = next(
        (issue for issue in financial_validation.issues if issue.type == "balance_mismatch"),
        None,
    )
    if mismatch is None:
        return extraction_by_page, financial_validation

    service = extraction_service or TransactionExtractionService()
    regions_by_page = {region.page: region for region in transaction_regions.transaction_regions}
    suspect_pages = sorted(
        page
        for page in regions_by_page
        if page not in verification_by_page or not verification_by_page[page].valid
    )
    ordered_pages = suspect_pages + sorted(
        page for page in regions_by_page if page not in suspect_pages
    )

    attempts: list[RecoveryAttempt] = []
    for page in ordered_pages:
        try:
            recovered = service.extract(
                document,
                regions_by_page[page],
                transaction_fields,
                previous_attempt=extraction_by_page.get(page),
                recovery_hint=mismatch.description,
            )
        except Exception:
            logger.warning("recovery: re-extraction failed for page %d", page, exc_info=True)
            attempts.append(RecoveryAttempt(page=page, succeeded=False))
            continue

        candidate = {**extraction_by_page, page: recovered}
        try:
            candidate_validation = validate(candidate)
        except Exception:
            logger.warning("recovery: re-validation failed for page %d", page, exc_info=True)
            attempts.append(RecoveryAttempt(page=page, succeeded=False))
            continue

        if candidate_validation.valid:
            attempts.append(RecoveryAttempt(page=page, succeeded=True))
            candidate_validation.recovery_attempts = attempts
            return candidate, candidate_validation
        attempts.append(RecoveryAttempt(page=page, succeeded=False))

    financial_validation.recovery_attempts = attempts
    return extraction_by_page, financial_validation
