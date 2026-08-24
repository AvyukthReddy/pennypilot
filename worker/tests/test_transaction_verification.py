import json

import pytest

from worker.document import Document, Page, TextBlock
from worker.extracted_transactions import TransactionExtraction
from worker.transaction_regions import TransactionRegion
from worker.transaction_verification import (
    TransactionVerificationError,
    TransactionVerificationService,
)


class _FakeProvider:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        return self._replies.pop(0)


HEADER_BLOCK = TextBlock(text="STATEMENT HEADER", x=45, y=20, width=200, height=12)
ROW_BLOCK = TextBlock(text="07/14/2026 Coffee $5.75", x=45, y=200, width=300, height=12)


def _make_document() -> Document:
    page = Page(
        page_number=2,
        width=612,
        height=792,
        text="",
        text_blocks=[HEADER_BLOCK, ROW_BLOCK],
        images=[],
    )
    return Document(
        statement_id="stmt-1",
        filename="statement.pdf",
        content_type="application/pdf",
        data=b"",
        file_hash="hash",
        size_bytes=0,
        page_count=2,
        parser_version="2",
        pages=[page],
        needs_ocr=False,
    )


def _make_region() -> TransactionRegion:
    return TransactionRegion(page=2, region=(45, 180, 570, 730))


def _make_extraction() -> TransactionExtraction:
    return TransactionExtraction(
        transactions=[
            {
                "transaction_date": "2026-07-14",
                "description": "Coffee",
                "amount": -5.75,
                "currency": "USD",
            },
        ],
    )


VALID_JSON = json.dumps({"valid": True, "issues": []})

INVALID_JSON = json.dumps(
    {
        "valid": False,
        "issues": [
            {
                "type": "missing_transaction",
                "page": 3,
                "description": "07/18 UBER TRIP",
            },
        ],
    }
)


def test_verify_valid_first_try() -> None:
    provider = _FakeProvider([VALID_JSON])
    service = TransactionVerificationService(provider=provider)

    result = service.verify(_make_document(), _make_region(), _make_extraction())

    assert result.valid is True
    assert result.issues == []
    assert len(provider.calls) == 1


def test_verify_invalid_with_issues() -> None:
    provider = _FakeProvider([INVALID_JSON])
    service = TransactionVerificationService(provider=provider)

    result = service.verify(_make_document(), _make_region(), _make_extraction())

    assert result.valid is False
    assert len(result.issues) == 1
    assert result.issues[0].type == "missing_transaction"
    assert result.issues[0].page == 3
    assert "UBER TRIP" in result.issues[0].description


def test_verify_prompt_includes_extracted_transactions() -> None:
    provider = _FakeProvider([VALID_JSON])
    service = TransactionVerificationService(provider=provider)

    service.verify(_make_document(), _make_region(), _make_extraction())

    user_content = provider.calls[0][1]["content"]
    text_parts = " ".join(part["text"] for part in user_content if part["type"] == "text")
    assert "Coffee" in text_parts
    assert "Extracted transactions" in text_parts


def test_verify_retries_after_invalid_then_succeeds() -> None:
    provider = _FakeProvider(["not json at all", VALID_JSON])
    service = TransactionVerificationService(provider=provider)

    result = service.verify(_make_document(), _make_region(), _make_extraction())

    assert result.valid is True
    assert len(provider.calls) == 2
    second_call_messages = provider.calls[1]
    assert any(
        "wasn't valid" in m["content"] for m in second_call_messages if m["role"] == "user"
    )


def test_verify_raises_after_exhausting_attempts() -> None:
    provider = _FakeProvider(["not json", "still not json"])
    service = TransactionVerificationService(provider=provider)

    with pytest.raises(TransactionVerificationError):
        service.verify(_make_document(), _make_region(), _make_extraction())
