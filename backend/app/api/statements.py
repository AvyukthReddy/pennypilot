import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.statement import Statement
from app.schemas.statement import StatementRead
from app.services.storage import delete_statement, get_statement_view_url, upload_statement

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
    )
    db.add(statement)
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
