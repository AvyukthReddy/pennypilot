import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class TransactionRead(BaseModel):
    id: uuid.UUID
    statement_id: uuid.UUID
    transaction_date: date
    post_date: date | None
    description: str
    amount: Decimal
    currency: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionListRead(BaseModel):
    items: list[TransactionRead]
    total: int
    limit: int
    offset: int
