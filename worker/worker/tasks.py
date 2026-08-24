import logging
import uuid
from dataclasses import asdict

import httpx

from worker.celery_app import app
from worker.db import SessionLocal
from worker.document import Document, Page
from worker.document_analysis import DocumentAnalysis
from worker.document_understanding import DocumentUnderstandingService
from worker.models import StatementRow, TransactionRow
from worker.pdf_analysis import analyze_pdf, is_scanned
from worker.transaction_extraction import TransactionExtractionService
from worker.transaction_region_detection import TransactionRegionDetectionService
from worker.transaction_regions import TransactionRegionDetection
from worker.transaction_schema import TransactionSchemaDiscovery
from worker.transaction_schema_discovery import TransactionSchemaDiscoveryService

logger = logging.getLogger(__name__)

# Bumped whenever the ingestion logic meaningfully changes, so documents
# processed by an older version of this pipeline can be told apart from
# ones processed by the current one (e.g. to decide what needs reprocessing
# once a real parser exists).
INGESTION_VERSION = "2"


@app.task(name="worker.ping")
def ping() -> str:
    return "pong"


@app.task(name="worker.parse_statement")
def parse_statement(statement_id: str, signed_url: str) -> None:
    """Phase 1+2+3+4+5+6: document ingestion, analysis, understanding,
    transaction-region detection, transaction-schema discovery, and
    transaction extraction. Downloads the stored file exactly as uploaded
    (never modified), analyzes PDFs page-by-page (size, text, positioned text
    blocks, image regions), flags scanned/image-only documents, classifies
    what the document is (bank/credit-card statement, institution, period,
    sections) via DocumentUnderstandingService, narrows the pages flagged
    "transactions" down to an exact bounding region per page via
    TransactionRegionDetectionService, figures out what a transaction record
    actually looks like in this document (which columns map to which fields)
    via TransactionSchemaDiscoveryService, then extracts every transaction
    row region-by-region via TransactionExtractionService and inserts them
    into the transactions table."""
    session = SessionLocal()
    try:
        stmt = session.get(StatementRow, uuid.UUID(statement_id))
        if stmt is None:
            return  # deleted before the task ran

        stmt.status = "processing"
        stmt.parse_error = None
        session.commit()

        try:
            response = httpx.get(signed_url, timeout=60)
            response.raise_for_status()
        except Exception:
            # Never surface str(exc) here — it can embed the signed URL/token.
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
                stmt.parse_error = "Could not read this PDF — it may be corrupt."
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
        # already succeeded by this point — a failure here (missing API key,
        # network error, model never returns valid JSON) must not fail the
        # statement, only leave it unclassified.
        document_analysis: DocumentAnalysis | None = None
        if stmt.content_type == "application/pdf" and not needs_ocr and pages:
            try:
                document_analysis = DocumentUnderstandingService().analyze(document)
            except Exception:
                logger.warning(
                    "statement %s: document understanding failed", statement_id, exc_info=True
                )
        # Same best-effort philosophy as document understanding above — a
        # failure here must not fail the statement, only leave it without
        # detected regions. Nothing to narrow if Phase 3 found no
        # "transactions" section (includes the needs_ocr/no-document_analysis
        # cases, inherited since those already skip document understanding).
        transaction_regions: TransactionRegionDetection | None = None
        if document_analysis and any(
            section.type == "transactions" for section in document_analysis.sections
        ):
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
        # Same best-effort philosophy again — a failure here must not fail
        # the statement, only leave it without a discovered schema. Nothing
        # to map if Phase 4 found no regions to narrow to.
        transaction_schema: TransactionSchemaDiscovery | None = None
        if transaction_regions and transaction_regions.transaction_regions:
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
        # page), not once per document — each call only needs that page's
        # cropped blocks plus the column mapping Phase 5 already discovered.
        # A single region failing (bad JSON after retries, network blip)
        # must not discard transactions already extracted from other
        # regions, so each region gets its own try/except.
        extracted_rows: list[TransactionRow] = []
        if transaction_schema and transaction_regions:
            for region in transaction_regions.transaction_regions:
                try:
                    extraction = TransactionExtractionService().extract(
                        document, region, transaction_schema.transaction_fields
                    )
                except Exception:
                    logger.warning(
                        "statement %s: transaction extraction failed for page %d",
                        statement_id,
                        region.page,
                        exc_info=True,
                    )
                    continue
                for txn in extraction.transactions:
                    extracted_rows.append(
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
