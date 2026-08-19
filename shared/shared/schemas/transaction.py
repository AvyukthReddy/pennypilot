from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ParsedTransaction(BaseModel):
    """A single validated transaction row, produced by the worker's parser stage
    before it's persisted. Deliberately excludes statement_id/user_id — those are
    persistence identifiers attached by the worker at insert time, not something
    the row-parsing stage should know."""

    transaction_date: date
    post_date: date | None = None
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal
    currency: str | None = None
    raw_row: str | None = None

    model_config = {"str_strip_whitespace": True}

    @field_validator("description")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter code")
        return v
