import logging
import uuid
from dataclasses import asdict

import httpx

from worker.celery_app import app
from worker.db import SessionLocal
from worker.document import Document, Page
from worker.document_analysis import DocumentAnalysis
from worker.document_understanding import DocumentUnderstandingService
from worker.models import StatementRow
from worker.pdf_analysis import analyze_pdf, is_scanned

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
    """Phase 1+2+3: document ingestion, analysis, and understanding. Downloads
    the stored file exactly as uploaded (never modified), analyzes PDFs
    page-by-page (size, text, positioned text blocks, image regions), flags
    scanned/image-only documents, then classifies what the document is
    (bank/credit-card statement, institution, period, sections) via
    DocumentUnderstandingService. No transaction-line parser exists yet;
    status lands on "ingested", not "parsed"."""
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
        # TODO(phase 4): hand `document` (+ document_analysis) to a real
        # transaction-line parser here.

        stmt.page_count = page_count
        stmt.parser_version = INGESTION_VERSION
        stmt.needs_ocr = needs_ocr
        stmt.pages = [asdict(page) for page in pages]
        stmt.document_analysis = (
            document_analysis.model_dump(mode="json") if document_analysis else None
        )
        stmt.status = "ingested"
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
