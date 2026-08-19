import json

import pytest

from worker.document import Document, Page
from worker.document_understanding import (
    DocumentUnderstandingError,
    DocumentUnderstandingService,
)


class _FakeProvider:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        return self._replies.pop(0)


def _make_document() -> Document:
    return Document(
        statement_id="stmt-1",
        filename="statement.pdf",
        content_type="application/pdf",
        data=b"",
        file_hash="hash",
        size_bytes=0,
        page_count=1,
        parser_version="2",
        pages=[
            Page(
                page_number=1,
                width=612,
                height=792,
                text="Chase checking statement",
                text_blocks=[],
                images=[],
            )
        ],
        needs_ocr=False,
    )


VALID_ANALYSIS_JSON = json.dumps(
    {
        "document_type": "bank_statement",
        "institution": "Chase",
        "account_type": "checking",
        "account_last4": "1234",
        "currency": "USD",
        "statement_start": "2026-07-01",
        "statement_end": "2026-07-31",
        "sections": [{"type": "transactions", "pages": [1]}],
    }
)


def test_analyze_valid_json_first_try() -> None:
    provider = _FakeProvider([VALID_ANALYSIS_JSON])
    service = DocumentUnderstandingService(provider=provider)

    result = service.analyze(_make_document())

    assert result.document_type == "bank_statement"
    assert result.institution == "Chase"
    assert result.sections[0].type == "transactions"
    assert len(provider.calls) == 1


def test_analyze_retries_after_invalid_then_succeeds() -> None:
    provider = _FakeProvider(["not json at all", VALID_ANALYSIS_JSON])
    service = DocumentUnderstandingService(provider=provider)

    result = service.analyze(_make_document())

    assert result.document_type == "bank_statement"
    assert len(provider.calls) == 2
    second_call_messages = provider.calls[1]
    assert any(
        "wasn't valid" in m["content"] for m in second_call_messages if m["role"] == "user"
    )


def test_analyze_strips_markdown_fence() -> None:
    fenced = f"```json\n{VALID_ANALYSIS_JSON}\n```"
    provider = _FakeProvider([fenced])
    service = DocumentUnderstandingService(provider=provider)

    result = service.analyze(_make_document())

    assert result.document_type == "bank_statement"


def test_analyze_raises_after_exhausting_attempts() -> None:
    provider = _FakeProvider(["not json", "still not json"])
    service = DocumentUnderstandingService(provider=provider)

    with pytest.raises(DocumentUnderstandingError):
        service.analyze(_make_document())
