from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ExtractedTransaction(BaseModel):
    transaction_date: date
    post_date: date | None = None
    description: str
    amount: Decimal
    currency: str | None = None


class TransactionExtraction(BaseModel):
    transactions: list[ExtractedTransaction]
