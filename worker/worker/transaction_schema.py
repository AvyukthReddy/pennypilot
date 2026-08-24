from typing import Literal

from pydantic import BaseModel

Semantics = Literal["debit", "credit", "amount"]


class FieldSource(BaseModel):
    """Where one target field's value actually lives in this document's table
    — a positional label the model assigns itself (left to right, from the
    coordinates it's shown), not something we pre-compute."""

    source: str  # e.g. "column_1"
    semantics: Semantics | None = None  # only meaningful for amount-like fields


class TransactionFields(BaseModel):
    """Maps this document's actual columns onto Transaction's fixed fields
    (backend/app/models/transaction.py) — the answer to "what does a
    transaction look like here?", not an extraction of any row's data.
    `amount` is a list because some tables split it across separate
    Debit/Credit columns; a single target field then needs two sources,
    each tagged with which side it came from."""

    transaction_date: FieldSource
    post_date: FieldSource | None = None
    description: FieldSource
    amount: list[FieldSource]
    currency: FieldSource | None = None


class TransactionSchemaDiscovery(BaseModel):
    transaction_fields: TransactionFields
