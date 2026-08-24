from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from worker.document_analysis import DocumentAnalysis
from worker.models import TransactionRow

FinancialIssueType = Literal[
    "invalid_date",
    "date_outside_period",
    "invalid_amount",
    "duplicate_transaction",
    "balance_mismatch",
]

# A generous static sanity range for transaction_date.year — deliberately
# not compared against date.today() so this stays fully deterministic and
# doesn't need time-mocking in tests.
MIN_REASONABLE_YEAR = 1990
MAX_REASONABLE_YEAR = 2100

BALANCE_TOLERANCE = Decimal("0.01")


class FinancialValidationIssue(BaseModel):
    type: FinancialIssueType
    description: str


class BalanceCheck(BaseModel):
    beginning_balance: Decimal
    net_change: Decimal
    expected_ending_balance: Decimal
    actual_ending_balance: Decimal
    reconciled: bool


class RecoveryAttempt(BaseModel):
    page: int
    succeeded: bool


class FinancialValidation(BaseModel):
    valid: bool
    issues: list[FinancialValidationIssue] = []
    balance_check: BalanceCheck | None = None
    recovery_attempts: list[RecoveryAttempt] = []


def _check_dates(
    transactions: list[TransactionRow], document_analysis: DocumentAnalysis | None
) -> list[FinancialValidationIssue]:
    issues: list[FinancialValidationIssue] = []
    for row in transactions:
        if row.post_date is not None and row.post_date < row.transaction_date:
            issues.append(
                FinancialValidationIssue(
                    type="invalid_date",
                    description=(
                        f"{row.transaction_date} '{row.description}': post_date "
                        f"{row.post_date} is before transaction_date"
                    ),
                )
            )
        if not (MIN_REASONABLE_YEAR <= row.transaction_date.year <= MAX_REASONABLE_YEAR):
            issues.append(
                FinancialValidationIssue(
                    type="invalid_date",
                    description=(
                        f"{row.transaction_date} '{row.description}': year is outside "
                        f"the plausible range {MIN_REASONABLE_YEAR}-{MAX_REASONABLE_YEAR}"
                    ),
                )
            )
        if (
            document_analysis
            and document_analysis.statement_start
            and document_analysis.statement_end
            and not (
                document_analysis.statement_start
                <= row.transaction_date
                <= document_analysis.statement_end
            )
        ):
            issues.append(
                FinancialValidationIssue(
                    type="date_outside_period",
                    description=(
                        f"{row.transaction_date} '{row.description}' falls outside "
                        f"the statement period {document_analysis.statement_start} to "
                        f"{document_analysis.statement_end}"
                    ),
                )
            )
    return issues


def _check_amounts(transactions: list[TransactionRow]) -> list[FinancialValidationIssue]:
    issues: list[FinancialValidationIssue] = []
    for row in transactions:
        if row.amount == 0:
            issues.append(
                FinancialValidationIssue(
                    type="invalid_amount",
                    description=f"{row.transaction_date} '{row.description}' has a zero amount",
                )
            )
        elif row.amount.as_tuple().exponent < -2:
            issues.append(
                FinancialValidationIssue(
                    type="invalid_amount",
                    description=(
                        f"{row.transaction_date} '{row.description}' amount "
                        f"{row.amount} has more than 2 decimal places"
                    ),
                )
            )
    return issues


def _check_duplicates(transactions: list[TransactionRow]) -> list[FinancialValidationIssue]:
    grouped: dict[tuple, list[TransactionRow]] = {}
    for row in transactions:
        key = (row.transaction_date, row.description, row.amount)
        grouped.setdefault(key, []).append(row)

    issues: list[FinancialValidationIssue] = []
    for (transaction_date, description, amount), rows in grouped.items():
        if len(rows) > 1:
            issues.append(
                FinancialValidationIssue(
                    type="duplicate_transaction",
                    description=(
                        f"{len(rows)} duplicate transactions: {transaction_date} "
                        f"'{description}' {amount}"
                    ),
                )
            )
    return issues


def _check_balance(
    transactions: list[TransactionRow], document_analysis: DocumentAnalysis | None
) -> tuple[list[FinancialValidationIssue], BalanceCheck | None]:
    if (
        document_analysis is None
        or document_analysis.beginning_balance is None
        or document_analysis.ending_balance is None
    ):
        return [], None

    net_change = sum((row.amount for row in transactions), Decimal("0"))
    expected_ending = document_analysis.beginning_balance + net_change
    reconciled = abs(expected_ending - document_analysis.ending_balance) < BALANCE_TOLERANCE

    balance_check = BalanceCheck(
        beginning_balance=document_analysis.beginning_balance,
        net_change=net_change,
        expected_ending_balance=expected_ending,
        actual_ending_balance=document_analysis.ending_balance,
        reconciled=reconciled,
    )

    if reconciled:
        return [], balance_check

    issue = FinancialValidationIssue(
        type="balance_mismatch",
        description=(
            f"Expected ending balance {expected_ending} (beginning "
            f"{document_analysis.beginning_balance} + net change {net_change}), "
            f"statement shows {document_analysis.ending_balance}"
        ),
    )
    return [issue], balance_check


def validate_transactions(
    document_analysis: DocumentAnalysis | None, transactions: list[TransactionRow]
) -> FinancialValidation:
    """Deterministic, non-AI validation of a statement's final transaction
    list: date/amount sanity, duplicates, and (when the statement states a
    beginning/ending balance) arithmetic reconciliation. Purely diagnostic —
    never blocks persistence or triggers re-extraction, just surfaces
    problems for review."""
    issues = _check_dates(transactions, document_analysis)
    issues += _check_amounts(transactions)
    issues += _check_duplicates(transactions)
    balance_issues, balance_check = _check_balance(transactions, document_analysis)
    issues += balance_issues

    return FinancialValidation(valid=len(issues) == 0, issues=issues, balance_check=balance_check)
