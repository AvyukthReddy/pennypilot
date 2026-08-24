import uuid
from datetime import date
from decimal import Decimal

from worker.document_analysis import DocumentAnalysis
from worker.financial_validation import validate_transactions
from worker.models import TransactionRow


def _row(
    transaction_date: date,
    description: str,
    amount: str,
    post_date: date | None = None,
) -> TransactionRow:
    return TransactionRow(
        id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        transaction_date=transaction_date,
        post_date=post_date,
        description=description,
        amount=Decimal(amount),
        currency="USD",
    )


def _analysis(**kwargs) -> DocumentAnalysis:
    return DocumentAnalysis(document_type="bank_statement", **kwargs)


def test_valid_transactions_produce_no_issues() -> None:
    transactions = [
        _row(date(2026, 7, 14), "Coffee", "-5.75"),
        _row(date(2026, 7, 15), "Groceries", "-42.10"),
    ]

    result = validate_transactions(None, transactions)

    assert result.valid is True
    assert result.issues == []
    assert result.balance_check is None


def test_post_date_before_transaction_date_is_invalid() -> None:
    transactions = [
        _row(date(2026, 7, 14), "Coffee", "-5.75", post_date=date(2026, 7, 10)),
    ]

    result = validate_transactions(None, transactions)

    assert result.valid is False
    assert len(result.issues) == 1
    assert result.issues[0].type == "invalid_date"
    assert "post_date" in result.issues[0].description


def test_year_out_of_plausible_range_is_invalid() -> None:
    transactions = [_row(date(1899, 7, 14), "Coffee", "-5.75")]

    result = validate_transactions(None, transactions)

    assert result.valid is False
    assert result.issues[0].type == "invalid_date"
    assert "plausible range" in result.issues[0].description


def test_date_outside_statement_period_is_flagged() -> None:
    transactions = [_row(date(2026, 8, 15), "Coffee", "-5.75")]
    analysis = _analysis(statement_start=date(2026, 7, 1), statement_end=date(2026, 7, 31))

    result = validate_transactions(analysis, transactions)

    assert result.valid is False
    assert result.issues[0].type == "date_outside_period"


def test_zero_amount_is_invalid() -> None:
    transactions = [_row(date(2026, 7, 14), "Coffee", "0")]

    result = validate_transactions(None, transactions)

    assert result.valid is False
    assert result.issues[0].type == "invalid_amount"
    assert "zero amount" in result.issues[0].description


def test_amount_with_extra_decimal_places_is_invalid() -> None:
    transactions = [_row(date(2026, 7, 14), "Coffee", "-5.755")]

    result = validate_transactions(None, transactions)

    assert result.valid is False
    assert result.issues[0].type == "invalid_amount"
    assert "decimal places" in result.issues[0].description


def test_duplicate_transactions_are_flagged() -> None:
    transactions = [
        _row(date(2026, 7, 14), "Coffee", "-5.75"),
        _row(date(2026, 7, 14), "Coffee", "-5.75"),
    ]

    result = validate_transactions(None, transactions)

    assert result.valid is False
    assert result.issues[0].type == "duplicate_transaction"
    assert "2 duplicate" in result.issues[0].description


def test_reconciled_balance_produces_no_issue() -> None:
    transactions = [
        _row(date(2026, 7, 5), "Deposit", "500"),
        _row(date(2026, 7, 10), "Rent", "-100"),
        _row(date(2026, 7, 20), "Coffee", "-20"),
    ]
    analysis = _analysis(beginning_balance=Decimal("1000"), ending_balance=Decimal("1380"))

    result = validate_transactions(analysis, transactions)

    assert result.valid is True
    assert result.balance_check is not None
    assert result.balance_check.reconciled is True
    assert result.balance_check.net_change == Decimal("380")
    assert result.balance_check.expected_ending_balance == Decimal("1380")


def test_balance_mismatch_is_flagged() -> None:
    transactions = [
        _row(date(2026, 7, 5), "Deposit", "500"),
        _row(date(2026, 7, 10), "Rent", "-100"),
        # Missing the -$20 coffee transaction the user's worked example describes.
    ]
    analysis = _analysis(beginning_balance=Decimal("1000"), ending_balance=Decimal("1380"))

    result = validate_transactions(analysis, transactions)

    assert result.valid is False
    assert result.balance_check is not None
    assert result.balance_check.reconciled is False
    assert result.balance_check.expected_ending_balance == Decimal("1400")
    assert any(issue.type == "balance_mismatch" for issue in result.issues)


def test_no_document_analysis_skips_period_and_balance_checks() -> None:
    transactions = [_row(date(2026, 7, 14), "Coffee", "-5.75")]

    result = validate_transactions(None, transactions)

    assert result.valid is True
    assert result.balance_check is None
