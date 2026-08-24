from typing import Literal

from pydantic import BaseModel

IssueType = Literal[
    "missing_transaction",
    "duplicate_transaction",
    "wrong_date",
    "wrong_amount",
    "wrong_sign",
    "split_or_merged_transaction",
    "other",
]


class VerificationIssue(BaseModel):
    type: IssueType
    page: int
    description: str


class TransactionVerification(BaseModel):
    valid: bool
    issues: list[VerificationIssue] = []
