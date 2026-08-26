import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StatementRead(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    parse_error: str | None = None
    page_count: int | None = None
    needs_ocr: bool | None = None
    processing_stage: str | None = None
    processing_detail: str | None = None
    document_type: Literal["bank_statement", "credit_card_statement", "unknown"] | None = None
    institution: str | None = None
    account_type_tags: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class TextBlockRead(BaseModel):
    text: str
    x: float
    y: float
    width: float
    height: float


class ImageRegionRead(BaseModel):
    x: float
    y: float
    width: float
    height: float


class PageRead(BaseModel):
    page_number: int
    width: float
    height: float
    text: str
    text_blocks: list[TextBlockRead]
    images: list[ImageRegionRead]


class StatementPagesRead(BaseModel):
    statement_id: uuid.UUID
    pages: list[PageRead]


class DocumentSectionRead(BaseModel):
    type: Literal["account_summary", "transactions", "fees", "interest", "disclosures", "other"]
    pages: list[int]


class DocumentAnalysisRead(BaseModel):
    document_type: Literal["bank_statement", "credit_card_statement", "unknown"]
    institution: str | None = None
    account_type: str | None = None
    account_last4: str | None = None
    currency: str | None = None
    statement_start: date | None = None
    statement_end: date | None = None
    beginning_balance: Decimal | None = None
    ending_balance: Decimal | None = None
    sections: list[DocumentSectionRead] = []


class StatementAnalysisRead(BaseModel):
    statement_id: uuid.UUID
    document_analysis: DocumentAnalysisRead | None


class TransactionRegionRead(BaseModel):
    page: int
    region: tuple[float, float, float, float]


class StatementTransactionRegionsRead(BaseModel):
    statement_id: uuid.UUID
    transaction_regions: list[TransactionRegionRead] | None


class FieldSourceRead(BaseModel):
    source: str
    semantics: Literal["debit", "credit", "amount"] | None = None


class TransactionFieldsRead(BaseModel):
    transaction_date: FieldSourceRead
    post_date: FieldSourceRead | None = None
    description: FieldSourceRead
    amount: list[FieldSourceRead]
    currency: FieldSourceRead | None = None


class StatementTransactionSchemaRead(BaseModel):
    statement_id: uuid.UUID
    transaction_fields: TransactionFieldsRead | None


class VerificationIssueRead(BaseModel):
    type: Literal[
        "missing_transaction",
        "duplicate_transaction",
        "wrong_date",
        "wrong_amount",
        "wrong_sign",
        "split_or_merged_transaction",
        "other",
    ]
    page: int
    description: str


class StatementTransactionVerificationRead(BaseModel):
    statement_id: uuid.UUID
    valid: bool | None
    issues: list[VerificationIssueRead]


class FinancialValidationIssueRead(BaseModel):
    type: Literal[
        "invalid_date",
        "date_outside_period",
        "invalid_amount",
        "duplicate_transaction",
        "balance_mismatch",
    ]
    description: str


class BalanceCheckRead(BaseModel):
    beginning_balance: Decimal
    net_change: Decimal
    expected_ending_balance: Decimal
    actual_ending_balance: Decimal
    reconciled: bool


class RecoveryAttemptRead(BaseModel):
    page: int
    succeeded: bool


class StatementFinancialValidationRead(BaseModel):
    statement_id: uuid.UUID
    valid: bool | None
    issues: list[FinancialValidationIssueRead]
    balance_check: BalanceCheckRead | None
    recovery_attempts: list[RecoveryAttemptRead] = []


class ConfidenceBreakdownRead(BaseModel):
    extraction: float
    verification: float
    financial_validation: float
    balance_reconciliation: float
    structural_consistency: float


class StatementConfidenceRead(BaseModel):
    statement_id: uuid.UUID
    score: float | None
    status: Literal["validated", "needs_review", "unreliable"] | None
    warnings: list[str]
    breakdown: ConfidenceBreakdownRead | None


CurrencySource = Literal["override", "detected", "default"]


class StatementCurrencyRead(BaseModel):
    statement_id: uuid.UUID
    currency: str
    source: CurrencySource
    detected_currency: str | None = None


class StatementCurrencyUpdate(BaseModel):
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _uppercase(cls, value: str | None) -> str | None:
        return value.upper() if value else None


FieldOverrideSource = Literal["override", "detected", "default"]


class StatementInstitutionRead(BaseModel):
    statement_id: uuid.UUID
    institution: str | None
    source: FieldOverrideSource
    detected_institution: str | None = None


class StatementInstitutionUpdate(BaseModel):
    institution: str | None = Field(default=None, max_length=255)

    @field_validator("institution")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class StatementAccountTypeTagsRead(BaseModel):
    statement_id: uuid.UUID
    account_type_tags: list[str]
    source: FieldOverrideSource
    detected_account_type_tags: list[str] = []


class StatementAccountTypeTagsUpdate(BaseModel):
    account_type_tags: list[str] | None = None

    @field_validator("account_type_tags")
    @classmethod
    def _clean(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in value:
            cleaned_tag = " ".join(tag.strip().lower().split())
            if cleaned_tag and cleaned_tag not in seen:
                seen.add(cleaned_tag)
                cleaned.append(cleaned_tag)
        return cleaned


class StatementProgressRead(BaseModel):
    statement_id: uuid.UUID
    status: str
    processing_stage: str | None
    processing_detail: str | None
    parse_error: str | None
