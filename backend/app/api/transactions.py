import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionListRead

router = APIRouter()


@router.get("/api/transactions", response_model=TransactionListRead)
def list_transactions(
    statement_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionListRead:
    filters = [Transaction.user_id == uuid.UUID(user.id)]
    if statement_id is not None:
        filters.append(Transaction.statement_id == statement_id)

    total = db.scalar(select(func.count()).select_from(Transaction).where(*filters)) or 0

    stmt = (
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(stmt))

    return TransactionListRead(items=items, total=total, limit=limit, offset=offset)
