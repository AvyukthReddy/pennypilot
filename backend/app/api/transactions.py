import math
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionListRead
from app.services.statement_fields import resolve_account_type_tags, resolve_institution

router = APIRouter()

SORTABLE_COLUMNS = {
    "transaction_date": Transaction.transaction_date,
    "amount": Transaction.amount,
    "description": Transaction.description,
    "created_at": Transaction.created_at,
}


def _matching_statement_ids(
    db: Session,
    user_id: uuid.UUID,
    document_type: list[str] | None,
    institution: list[str] | None,
    account_type_tag: list[str] | None,
) -> list[uuid.UUID] | None:
    """Resolves every one of the user's statements' effective document_type/
    institution/account_type_tags in Python (override resolution isn't
    expressible as a plain WHERE clause) and returns the ids matching all given
    filters (OR within one filter's values, AND across the three filter
    dimensions), or None if none of the three filters were requested."""
    if not (document_type or institution or account_type_tag):
        return None

    statements = list(db.scalars(select(Statement).where(Statement.user_id == user_id)))
    doctype_set = set(document_type) if document_type else None
    institution_set = set(institution) if institution else None
    tag_set = set(account_type_tag) if account_type_tag else None

    matching: list[uuid.UUID] = []
    for s in statements:
        if doctype_set is not None:
            doc_type = s.document_analysis.get("document_type") if s.document_analysis else None
            if doc_type not in doctype_set:
                continue
        if institution_set is not None:
            resolved_institution, _, _ = resolve_institution(s)
            if resolved_institution not in institution_set:
                continue
        if tag_set is not None:
            resolved_tags, _, _ = resolve_account_type_tags(s)
            if not (tag_set & set(resolved_tags)):
                continue
        matching.append(s.id)
    return matching


@router.get("/api/transactions", response_model=TransactionListRead)
def list_transactions(
    statement_id: uuid.UUID | None = None,
    document_name: list[str] | None = Query(None),
    document_type: list[Literal["bank_statement", "credit_card_statement", "unknown"]]
    | None = Query(None),
    institution: list[str] | None = Query(None),
    account_type_tag: list[str] | None = Query(None),
    type: Literal["credit", "debit"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_by: Literal["transaction_date", "amount", "description", "created_at"] = "transaction_date",
    sort_order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionListRead:
    filters = [Transaction.user_id == uuid.UUID(user.id)]
    if statement_id is not None:
        filters.append(Transaction.statement_id == statement_id)
    if type == "credit":
        filters.append(Transaction.amount > 0)
    elif type == "debit":
        filters.append(Transaction.amount < 0)
    if start_date is not None:
        filters.append(Transaction.transaction_date >= start_date)
    if end_date is not None:
        filters.append(Transaction.transaction_date <= end_date)

    matching_ids = _matching_statement_ids(
        db, uuid.UUID(user.id), document_type, institution, account_type_tag
    )
    if matching_ids is not None:
        filters.append(Transaction.statement_id.in_(matching_ids))

    base = select(Transaction).where(*filters)
    count_base = select(func.count()).select_from(Transaction).where(*filters)
    if document_name:
        base = base.join(Statement, Transaction.statement_id == Statement.id)
        count_base = count_base.join(Statement, Transaction.statement_id == Statement.id)
        name_filter = Statement.filename.in_(document_name)
        base = base.where(name_filter)
        count_base = count_base.where(name_filter)

    total = db.scalar(count_base) or 0
    total_pages = math.ceil(total / page_size) if total else 0

    order_column = SORTABLE_COLUMNS[sort_by]
    order_fn = asc if sort_order == "asc" else desc
    stmt = (
        base.order_by(order_fn(order_column), Transaction.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    items = list(db.scalars(stmt))

    return TransactionListRead(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)
