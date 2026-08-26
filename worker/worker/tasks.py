import logging
import uuid
from dataclasses import asdict

import httpx
from sqlalchemy.orm import Session

from worker.celery_app import app
from worker.confidence import compute_confidence
from worker.db import SessionLocal
from worker.document import Document, Page
from worker.document_analysis import DocumentAnalysis
from worker.document_understanding import DocumentUnderstandingService
from worker.extracted_transactions import TransactionExtraction
from worker.financial_validation import validate_transactions
from worker.models import StatementRow, TransactionRow
from worker.pdf_analysis import analyze_pdf, is_scanned
from worker.recovery import attempt_recovery
from worker.transaction_extraction import TransactionExtractionService
from worker.transaction_region_detection import TransactionRegionDetectionService
from worker.transaction_regions import TransactionRegionDetection
from worker.transaction_schema import TransactionSchemaDiscovery
from worker.transaction_schema_discovery import TransactionSchemaDiscoveryService
from worker.transaction_verification import TransactionVerificationService
from worker.verification_issues import TransactionVerification

logger = logging.getLogger(__name__)

# Bumped whenever the ingestion logic meaningfully changes, so documents
# processed by an older version of this pipeline can be told apart from
# ones processed by the current one (e.g. to decide what needs reprocessing
# once a real parser exists).
INGESTION_VERSION = "2"

# Fixed, ordered set of pipeline phases surfaced to the frontend as a
# GitHub-Actions-style step list. Each stage's _set_stage(...) call sits at
# the very top of that phase's existing guard, before its try/except, so a
# stage reads as "reached" even if the AI call inside it goes on to fail. A
# guard that evaluates false simply never calls _set_stage for that phase,
# so the next phase whose guard passes is the one the frontend sees next,
# no separate "skipped" bookkeeping needed.
PROCESSING_STAGES = (
    "ingesting",
    "understanding",
    "detecting_regions",
    "discovering_schema",
    "extracting",
    "validating",
    "scoring_confidence",
)


def _set_stage(session: Session, stmt: StatementRow, stage: str, detail: str | None = None) -> None:
    stmt.processing_stage = stage
    stmt.processing_detail = detail
    session.commit()


@app.task(name="worker.ping")
def ping() -> str:
    return "pong"


@app.task(name="worker.parse_statement")
def parse_statement(statement_id: str, signed_url: str) -> None:
    """Phase 1+2+3+4+5+6+7+8+9+10: document ingestion, analysis,
    understanding, transaction-region detection, transaction-schema
    discovery, transaction extraction, transaction verification,
    deterministic financial validation, targeted recovery, and a final
    composite confidence score. Downloads the stored file exactly as
    uploaded (never modified), analyzes PDFs page-by-page (size, text,
    positioned text blocks, image regions), flags scanned/image-only
    documents, classifies what the document is (bank/credit-card statement,
    institution, period, sections, beginning/ending balance) via
    DocumentUnderstandingService, narrows the pages flagged "transactions"
    down to an exact bounding region per page via
    TransactionRegionDetectionService, figures out what a transaction
    record actually looks like in this document (which columns map to
    which fields) via TransactionSchemaDiscoveryService, extracts every
    transaction row region-by-region via TransactionExtractionService,
    checks each region's extraction against the region itself via
    TransactionVerificationService (re-extracting once with the found
    issues as correction feedback when invalid), runs a plain Python
    (non-AI) reconciliation pass over the result via validate_transactions,
    and, when that reconciliation fails with a balance mismatch,
    re-extracts the most-suspect region(s) one at a time via
    attempt_recovery until the numbers reconcile or every candidate has
    been tried. Finally, compute_confidence combines all of the above
    (extraction completeness, verification cleanliness, financial-
    validation issues, balance reconciliation, structural consistency) into
    one deterministic score before inserting the final rows into the
    transactions table. Commits stmt.processing_stage/processing_detail as
    each phase begins (see PROCESSING_STAGES) so a client polling the API
    mid-run can show live progress."""
    session = SessionLocal()
    try:
        stmt = session.get(StatementRow, uuid.UUID(statement_id))
        if stmt is None:
            return  # deleted before the task ran

        stmt.status = "processing"
        stmt.parse_error = None
        stmt.processing_stage = "ingesting"
        stmt.processing_detail = None
        session.commit()

        try:
            response = httpx.get(signed_url, timeout=60)
            response.raise_for_status()
        except Exception:
            # Never surface str(exc) here, it can embed the signed URL/token.
            stmt.status = "failed"
            stmt.parse_error = "Failed to download the statement file."
            session.commit()
            return
        data = response.content

        pages: list[Page] = []
        if stmt.content_type == "application/pdf":
            try:
                pages = analyze_pdf(data)
            except Exception:
                stmt.status = "failed"
                stmt.parse_error = "Could not read this PDF, it may be corrupt."
                session.commit()
                return

        page_count = len(pages) if pages else None
        needs_ocr = is_scanned(pages)

        document = Document(
            statement_id=str(stmt.id),
            filename=stmt.filename,
            content_type=stmt.content_type,
            data=data,
            file_hash=stmt.file_hash or "",
            size_bytes=len(data),
            page_count=page_count,
            parser_version=INGESTION_VERSION,
            pages=pages,
            needs_ocr=needs_ocr,
        )
        logger.info(
            "statement %s: analyzed (%d pages, %d text blocks, needs_ocr=%s)",
            statement_id,
            document.page_count or 0,
            sum(len(page.text_blocks) for page in document.pages),
            document.needs_ocr,
        )

        # Best-effort classification, not a transaction parser. Ingestion has
        # already succeeded by this point, a failure here (missing API key,
        # network error, model never returns valid JSON) must not fail the
        # statement, only leave it unclassified.
        document_analysis: DocumentAnalysis | None = None
        if stmt.content_type == "application/pdf" and not needs_ocr and pages:
            _set_stage(session, stmt, "understanding")
            try:
                document_analysis = DocumentUnderstandingService().analyze(document)
            except Exception:
                logger.warning(
                    "statement %s: document understanding failed", statement_id, exc_info=True
                )
        # Same best-effort philosophy as document understanding above, a
        # failure here must not fail the statement, only leave it without
        # detected regions. Nothing to narrow if Phase 3 found no
        # "transactions" section (includes the needs_ocr/no-document_analysis
        # cases, inherited since those already skip document understanding).
        transaction_regions: TransactionRegionDetection | None = None
        if document_analysis and any(
            section.type == "transactions" for section in document_analysis.sections
        ):
            _set_stage(session, stmt, "detecting_regions")
            try:
                transaction_regions = TransactionRegionDetectionService().detect(
                    document, document_analysis
                )
            except Exception:
                logger.warning(
                    "statement %s: transaction region detection failed",
                    statement_id,
                    exc_info=True,
                )
        # Same best-effort philosophy again, a failure here must not fail
        # the statement, only leave it without a discovered schema. Nothing
        # to map if Phase 4 found no regions to narrow to.
        transaction_schema: TransactionSchemaDiscovery | None = None
        if transaction_regions and transaction_regions.transaction_regions:
            _set_stage(session, stmt, "discovering_schema")
            try:
                transaction_schema = TransactionSchemaDiscoveryService().discover(
                    document, transaction_regions
                )
            except Exception:
                logger.warning(
                    "statement %s: transaction schema discovery failed",
                    statement_id,
                    exc_info=True,
                )
        # Extraction runs once per detected region (i.e. once per flagged
        # page), not once per document, each call only needs that page's
        # cropped blocks plus the column mapping Phase 5 already discovered.
        # A single region failing (bad JSON after retries, network blip)
        # must not discard transactions already extracted from other
        # regions, so each region gets its own try/except.
        extraction_by_page: dict[int, TransactionExtraction] = {}
        verification_by_page: dict[int, TransactionVerification] = {}
        verification_reports: list[TransactionVerification] = []
        statement_period = (
            (document_analysis.statement_start, document_analysis.statement_end)
            if document_analysis
            and document_analysis.statement_start
            and document_analysis.statement_end
            else None
        )
        if transaction_schema and transaction_regions:
            regions = transaction_regions.transaction_regions
            _set_stage(session, stmt, "extracting")
            for index, region in enumerate(regions, start=1):
                _set_stage(
                    session, stmt, "extracting", detail=f"Region {index} of {len(regions)}"
                )
                try:
                    extraction = TransactionExtractionService().extract(
                        document,
                        region,
                        transaction_schema.transaction_fields,
                        statement_period=statement_period,
                    )
                except Exception:
                    logger.warning(
                        "statement %s: transaction extraction failed for page %d",
                        statement_id,
                        region.page,
                        exc_info=True,
                    )
                    continue

                # Verification is best-effort on top of an already-succeeded
                # extraction: a failure here just means this region's
                # extraction is used as-is, uncorrected. When verification
                # does run and flags problems, extraction is retried once
                # with those issues as correction feedback; that retry's
                # output is trusted and persisted whether or not it's still
                # flagged (no re-verification loop).
                try:
                    verification = TransactionVerificationService().verify(
                        document, region, extraction
                    )
                except Exception:
                    logger.warning(
                        "statement %s: transaction verification failed for page %d",
                        statement_id,
                        region.page,
                        exc_info=True,
                    )
                    verification = None

                if verification is not None:
                    verification_reports.append(verification)
                    verification_by_page[region.page] = verification
                    if not verification.valid:
                        try:
                            extraction = TransactionExtractionService().extract(
                                document,
                                region,
                                transaction_schema.transaction_fields,
                                statement_period=statement_period,
                                previous_attempt=extraction,
                                verification_issues=verification.issues,
                            )
                        except Exception:
                            logger.warning(
                                "statement %s: corrective re-extraction failed for page %d",
                                statement_id,
                                region.page,
                                exc_info=True,
                            )

                extraction_by_page[region.page] = extraction

        def _rows_from_extractions(
            by_page: dict[int, TransactionExtraction],
        ) -> list[TransactionRow]:
            return [
                TransactionRow(
                    statement_id=stmt.id,
                    user_id=stmt.user_id,
                    transaction_date=txn.transaction_date,
                    post_date=txn.post_date,
                    description=txn.description,
                    amount=txn.amount,
                    currency=txn.currency
                    or (document_analysis.currency if document_analysis else None),
                )
                for extraction in by_page.values()
                for txn in extraction.transactions
            ]

        extracted_rows: list[TransactionRow] = _rows_from_extractions(extraction_by_page)

        # Pure Python, no AI call. Checks the final (possibly Phase-7-
        # corrected) transaction list for date/amount sanity, duplicates,
        # and (when the statement states one) balance reconciliation.
        # Purely diagnostic: never blocks persistence, never touches status.
        financial_validation = None
        if extracted_rows:
            _set_stage(session, stmt, "validating")
            try:
                financial_validation = validate_transactions(document_analysis, extracted_rows)
            except Exception:
                logger.warning(
                    "statement %s: financial validation failed", statement_id, exc_info=True
                )

        # When reconciliation failed with a balance mismatch, re-extract the
        # most-suspect region(s) one at a time (cheap, one AI call each)
        # instead of leaving a known-bad statement alone or reprocessing
        # everything. Stops as soon as one candidate reconciles; gives up
        # (keeping the original rows/validation) if none do. Best-effort,
        # attempt_recovery already isolates each candidate's own failures,
        # this try/except only guards against something unexpected.
        if (
            financial_validation
            and not financial_validation.valid
            and transaction_schema
            and transaction_regions
        ):
            try:
                extraction_by_page, financial_validation = attempt_recovery(
                    document,
                    transaction_regions,
                    transaction_schema.transaction_fields,
                    extraction_by_page,
                    verification_by_page,
                    financial_validation,
                    validate=lambda candidate: validate_transactions(
                        document_analysis, _rows_from_extractions(candidate)
                    ),
                    extraction_service=TransactionExtractionService(),
                    statement_period=statement_period,
                )
                extracted_rows = _rows_from_extractions(extraction_by_page)
            except Exception:
                logger.warning(
                    "statement %s: recovery failed", statement_id, exc_info=True
                )

        # Pure Python, no AI call. Combines the signals gathered above into
        # one deterministic score, not an LLM self-report. Gated on the same
        # condition as region detection: nothing to score when there was no
        # "transactions" section to begin with.
        confidence = None
        if document_analysis and any(
            section.type == "transactions" for section in document_analysis.sections
        ):
            _set_stage(session, stmt, "scoring_confidence")
            try:
                confidence = compute_confidence(
                    document_analysis,
                    transaction_regions,
                    extraction_by_page,
                    verification_by_page,
                    financial_validation,
                )
            except Exception:
                logger.warning(
                    "statement %s: confidence computation failed", statement_id, exc_info=True
                )

        stmt.page_count = page_count
        stmt.parser_version = INGESTION_VERSION
        stmt.needs_ocr = needs_ocr
        stmt.pages = [
            {key: value for key, value in asdict(page).items() if key != "image"}
            for page in pages
        ]
        stmt.document_analysis = (
            document_analysis.model_dump(mode="json") if document_analysis else None
        )
        stmt.transaction_regions = (
            transaction_regions.model_dump(mode="json") if transaction_regions else None
        )
        stmt.transaction_schema = (
            transaction_schema.model_dump(mode="json") if transaction_schema else None
        )
        stmt.transaction_verification = (
            TransactionVerification(
                valid=all(report.valid for report in verification_reports),
                issues=[issue for report in verification_reports for issue in report.issues],
            ).model_dump(mode="json")
            if verification_reports
            else None
        )
        stmt.financial_validation = (
            financial_validation.model_dump(mode="json") if financial_validation else None
        )
        stmt.confidence = confidence.model_dump(mode="json") if confidence else None
        stmt.status = "ingested"
        session.add_all(extracted_rows)
        session.commit()
    except Exception as exc:
        session.rollback()
        stmt = session.get(StatementRow, uuid.UUID(statement_id))
        if stmt is not None:
            stmt.status = "failed"
            stmt.parse_error = str(exc)[:500]
            session.commit()
        raise
    finally:
        session.close()
