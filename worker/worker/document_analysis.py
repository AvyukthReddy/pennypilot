from datetime import date
from typing import Literal

from pydantic import BaseModel

SectionType = Literal[
    "account_summary",
    "transactions",
    "fees",
    "interest",
    "disclosures",
    "other",
]


class DocumentSection(BaseModel):
    type: SectionType
    pages: list[int]


class DocumentAnalysis(BaseModel):
    """What kind of statement this is and where its sections live — the answer to
    "what is this document?", not a transaction extraction. A closed schema so the
    model can't hand back arbitrary JSON."""

    document_type: Literal["bank_statement", "credit_card_statement", "unknown"]
    institution: str | None = None
    account_type: str | None = None
    account_last4: str | None = None
    currency: str | None = None
    statement_start: date | None = None
    statement_end: date | None = None
    sections: list[DocumentSection] = []
