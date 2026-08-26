import uuid

from app.models.statement import Statement
from app.services.statement_fields import (
    normalize_account_type_tags,
    resolve_account_type_tags,
    resolve_institution,
)


def _make_statement(**overrides) -> Statement:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="statement.pdf",
        storage_path="path",
        content_type="application/pdf",
        size_bytes=100,
        document_analysis=None,
        institution=None,
        account_type_tags=None,
    )
    defaults.update(overrides)
    return Statement(**defaults)


def test_normalize_account_type_tags_keeps_credit_card_as_single_tag() -> None:
    assert normalize_account_type_tags("credit_card") == ["credit card"]
    assert normalize_account_type_tags("credit card") == ["credit card"]


def test_normalize_account_type_tags_splits_on_and() -> None:
    assert normalize_account_type_tags("checking_and_savings") == ["checking", "savings"]


def test_normalize_account_type_tags_handles_mixed_casing() -> None:
    assert normalize_account_type_tags("Checking_And_Savings") == ["checking", "savings"]


def test_normalize_account_type_tags_splits_on_ampersand_and_comma() -> None:
    assert normalize_account_type_tags("Checking & Savings") == ["checking", "savings"]
    assert normalize_account_type_tags("checking, savings") == ["checking", "savings"]


def test_normalize_account_type_tags_dedups() -> None:
    assert normalize_account_type_tags("savings_and_savings") == ["savings"]


def test_normalize_account_type_tags_handles_none_and_blank() -> None:
    assert normalize_account_type_tags(None) == []
    assert normalize_account_type_tags("") == []
    assert normalize_account_type_tags("   ") == []


def test_resolve_institution_prefers_override() -> None:
    statement = _make_statement(
        institution="My Bank", document_analysis={"institution": "Chase"}
    )
    institution, source, detected = resolve_institution(statement)
    assert institution == "My Bank"
    assert source == "override"
    assert detected == "Chase"


def test_resolve_institution_falls_back_to_detected() -> None:
    statement = _make_statement(institution=None, document_analysis={"institution": "Chase"})
    institution, source, detected = resolve_institution(statement)
    assert institution == "Chase"
    assert source == "detected"
    assert detected == "Chase"


def test_resolve_institution_defaults_to_none_when_nothing_known() -> None:
    statement = _make_statement(institution=None, document_analysis=None)
    institution, source, detected = resolve_institution(statement)
    assert institution is None
    assert source == "default"
    assert detected is None


def test_resolve_account_type_tags_prefers_override() -> None:
    statement = _make_statement(
        account_type_tags=["custom"], document_analysis={"account_type": "checking_and_savings"}
    )
    tags, source, detected = resolve_account_type_tags(statement)
    assert tags == ["custom"]
    assert source == "override"
    assert detected == ["checking", "savings"]


def test_resolve_account_type_tags_falls_back_to_detected_and_normalizes() -> None:
    statement = _make_statement(
        account_type_tags=None, document_analysis={"account_type": "checking_and_savings"}
    )
    tags, source, detected = resolve_account_type_tags(statement)
    assert tags == ["checking", "savings"]
    assert source == "detected"
    assert detected == ["checking", "savings"]


def test_resolve_account_type_tags_defaults_to_empty_when_nothing_known() -> None:
    statement = _make_statement(account_type_tags=None, document_analysis=None)
    tags, source, detected = resolve_account_type_tags(statement)
    assert tags == []
    assert source == "default"
    assert detected == []


def test_resolve_account_type_tags_explicit_empty_override_does_not_fall_back() -> None:
    statement = _make_statement(
        account_type_tags=[], document_analysis={"account_type": "checking_and_savings"}
    )
    tags, source, detected = resolve_account_type_tags(statement)
    assert tags == []
    assert source == "override"
    assert detected == ["checking", "savings"]
