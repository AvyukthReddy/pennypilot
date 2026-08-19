import logging
import uuid

import httpx

from worker.celery_app import app
from worker.db import SessionLocal
from worker.document import Document
from worker.models import StatementRow
from worker.pdf_info import count_pdf_pages

logger = logging.getLogger(__name__)

# Bumped whenever the ingestion logic meaningfully changes, so documents
# processed by an older version of this pipeline can be told apart from
# ones processed by the current one (e.g. to decide what needs reprocessing
# once a real parser exists).
INGESTION_VERSION = "1"


@app.task(name="worker.ping")
def ping() -> str:
    return "pong"


@app.task(name="worker.parse_statement")
def parse_statement(statement_id: str, signed_url: str) -> None:
    """Phase 1: document ingestion only. Downloads the stored file exactly
    as uploaded (never modified), records its page count (PDFs) and the
    ingestion version, and builds a Document — the handoff object a future
    parser will consume. No parser exists yet, so the task stops once
    ingestion succeeds; status lands on "ingested", not "parsed"."""
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

        page_count: int | None = None
        if stmt.content_type == "application/pdf":
            try:
                page_count = count_pdf_pages(data)
            except Exception:
                stmt.status = "failed"
                stmt.parse_error = "Could not read this PDF — it may be corrupt."
                session.commit()
                return

        document = Document(
            statement_id=str(stmt.id),
            filename=stmt.filename,
            content_type=stmt.content_type,
            data=data,
            file_hash=stmt.file_hash or "",
            size_bytes=len(data),
            page_count=page_count,
            parser_version=INGESTION_VERSION,
        )
        # TODO(phase 2): hand `document` to a real parser here.
        logger.info(
            "statement %s: ingested (%d bytes, %s pages)",
            statement_id,
            document.size_bytes,
            document.page_count,
        )

        stmt.page_count = page_count
        stmt.parser_version = INGESTION_VERSION
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
