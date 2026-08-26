import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery_client import enqueue_parse_statement
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.statement import Statement
from app.schemas.statement import (
    StatementAnalysisRead,
    StatementConfidenceRead,
    StatementCurrencyRead,
    StatementCurrencyUpdate,
    StatementFinancialValidationRead,
    StatementPagesRead,
    StatementProgressRead,
    StatementRead,
    StatementTransactionRegionsRead,
    StatementTransactionSchemaRead,
    StatementTransactionVerificationRead,
)
from app.services.storage import delete_statement, get_statement_view_url, upload_statement

# Signed URL passed to the parse task: long enough to survive a queue backlog,
# short enough to limit the exposure window of a URL that grants file access.
PARSE_TASK_URL_EXPIRY_SECONDS = 600

# Fallback when neither a user override nor AI-detected currency is
# available, so amount displays never show a bare, unit-less number.
DEFAULT_CURRENCY = "USD"


def _resolve_currency(statement: Statement) -> tuple[str, str, str | None]:
    """Returns (effective_currency, source, detected_currency)."""
    detected = (
        statement.document_analysis.get("currency") if statement.document_analysis else None
    )
    if statement.currency:
        return statement.currency, "override", detected
    if detected:
        return detected, "detected", detected
    return DEFAULT_CURRENCY, "default", detected

router = APIRouter()


def _get_owned_statement(statement_id: uuid.UUID, user: CurrentUser, db: Session) -> Statement:
    statement = db.get(Statement, statement_id)
    if statement is None or statement.user_id != uuid.UUID(user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Statement not found")
    return statement


@router.get("/api/statements", response_model=list[StatementRead])
def list_statements(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Statement]:
    stmt = (
        select(Statement)
        .where(Statement.user_id == uuid.UUID(user.id))
        .order_by(Statement.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.post("/api/statements", response_model=StatementRead)
def upload_statement_file(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Statement:
    data = file.file.read()
    file_hash = hashlib.sha256(data).hexdigest()

    duplicate = db.scalar(
        select(Statement).where(
            Statement.user_id == uuid.UUID(user.id), Statement.file_hash == file_hash
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This file has already been uploaded"
        )

    statement_id = uuid.uuid4()
    storage_path = upload_statement(
        user_id=user.id,
        statement_id=statement_id,
        token=user.token,
        content_type=file.content_type or "",
        data=data,
    )

    statement = Statement(
        id=statement_id,
        user_id=uuid.UUID(user.id),
        filename=file.filename or "statement",
        storage_path=storage_path,
        content_type=file.content_type or "",
        size_bytes=len(data),
        file_hash=file_hash,
    )
    db.add(statement)
    db.commit()
    db.refresh(statement)

    try:
        signed_url = get_statement_view_url(
            token=user.token,
            storage_path=storage_path,
            expires_in=PARSE_TASK_URL_EXPIRY_SECONDS,
        )
        enqueue_parse_statement(statement_id=str(statement.id), signed_url=signed_url)
    except Exception:
        # The upload already succeeded and is durably stored; failing to kick off
        # parsing shouldn't fail the request. The statement simply stays "uploaded",
        # a documented, meaningful state ("file exists, parsing not queued yet"),
        # rather than a silent, undocumented dead end. No automatic retry this pass.
        pass
    else:
        statement.status = "queued"
        db.commit()
        db.refresh(statement)

    return statement


@router.get("/api/statements/{statement_id}/view")
def view_statement_file(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    statement = _get_owned_statement(statement_id, user, db)
    url = get_statement_view_url(token=user.token, storage_path=statement.storage_path)
    return {"url": url}


@router.get("/api/statements/{statement_id}/pages", response_model=StatementPagesRead)
def get_statement_pages(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    return {"statement_id": statement.id, "pages": statement.pages or []}


@router.get("/api/statements/{statement_id}/progress", response_model=StatementProgressRead)
def get_statement_progress(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    return {
        "statement_id": statement.id,
        "status": statement.status,
        "processing_stage": statement.processing_stage,
        "processing_detail": statement.processing_detail,
        "parse_error": statement.parse_error,
    }


@router.get("/api/statements/{statement_id}/analysis", response_model=StatementAnalysisRead)
def get_statement_analysis(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    return {"statement_id": statement.id, "document_analysis": statement.document_analysis}


@router.get(
    "/api/statements/{statement_id}/transaction-regions",
    response_model=StatementTransactionRegionsRead,
)
def get_statement_transaction_regions(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    regions = (
        statement.transaction_regions["transaction_regions"]
        if statement.transaction_regions
        else None
    )
    return {"statement_id": statement.id, "transaction_regions": regions}


@router.get(
    "/api/statements/{statement_id}/transaction-schema",
    response_model=StatementTransactionSchemaRead,
)
def get_statement_transaction_schema(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    fields = (
        statement.transaction_schema["transaction_fields"]
        if statement.transaction_schema
        else None
    )
    return {"statement_id": statement.id, "transaction_fields": fields}


@router.get(
    "/api/statements/{statement_id}/transaction-verification",
    response_model=StatementTransactionVerificationRead,
)
def get_statement_transaction_verification(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    verification = statement.transaction_verification
    return {
        "statement_id": statement.id,
        "valid": verification["valid"] if verification else None,
        "issues": verification["issues"] if verification else [],
    }


@router.get(
    "/api/statements/{statement_id}/financial-validation",
    response_model=StatementFinancialValidationRead,
)
def get_statement_financial_validation(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    validation = statement.financial_validation
    return {
        "statement_id": statement.id,
        "valid": validation["valid"] if validation else None,
        "issues": validation["issues"] if validation else [],
        "balance_check": validation["balance_check"] if validation else None,
        # .get, not []: statements ingested before Phase 9 have a persisted
        # financial_validation blob with no recovery_attempts key at all.
        "recovery_attempts": validation.get("recovery_attempts", []) if validation else [],
    }


@router.get(
    "/api/statements/{statement_id}/confidence",
    response_model=StatementConfidenceRead,
)
def get_statement_confidence(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    confidence = statement.confidence
    return {
        "statement_id": statement.id,
        "score": confidence["score"] if confidence else None,
        "status": confidence["status"] if confidence else None,
        "warnings": confidence["warnings"] if confidence else [],
        "breakdown": confidence["breakdown"] if confidence else None,
    }


@router.get(
    "/api/statements/{statement_id}/currency",
    response_model=StatementCurrencyRead,
)
def get_statement_currency(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    currency, source, detected = _resolve_currency(statement)
    return {
        "statement_id": statement.id,
        "currency": currency,
        "source": source,
        "detected_currency": detected,
    }


@router.patch(
    "/api/statements/{statement_id}/currency",
    response_model=StatementCurrencyRead,
)
def update_statement_currency(
    statement_id: uuid.UUID,
    body: StatementCurrencyUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = _get_owned_statement(statement_id, user, db)
    statement.currency = body.currency
    db.commit()
    db.refresh(statement)
    currency, source, detected = _resolve_currency(statement)
    return {
        "statement_id": statement.id,
        "currency": currency,
        "source": source,
        "detected_currency": detected,
    }


@router.delete("/api/statements/{statement_id}")
def delete_statement_file(
    statement_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, uuid.UUID]:
    statement = _get_owned_statement(statement_id, user, db)

    delete_statement(token=user.token, storage_path=statement.storage_path)
    db.delete(statement)
    db.commit()
    return {"id": statement_id}
