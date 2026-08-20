import json

import pytest

from worker.document import Document, Page, TextBlock
from worker.document_analysis import DocumentAnalysis
from worker.transaction_region_detection import (
    TransactionRegionDetectionError,
    TransactionRegionDetectionService,
)


class _FakeProvider:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        return self._replies.pop(0)


def _page(number: int, text: str) -> Page:
    return Page(
        page_number=number,
        width=612,
        height=792,
        text=text,
        text_blocks=[TextBlock(text=text, x=45, y=180, width=100, height=12)],
        images=[],
    )


def _make_document() -> Document:
    return Document(
        statement_id="stmt-1",
        filename="statement.pdf",
        content_type="application/pdf",
        data=b"",
        file_hash="hash",
        size_bytes=0,
        page_count=3,
        parser_version="2",
        pages=[
            _page(1, "Account Summary"),
            _page(2, "07/14/2026 Coffee $5.75"),
            _page(3, "07/15/2026 Groceries $42.10"),
        ],
        needs_ocr=False,
    )


def _make_analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        document_type="bank_statement",
        sections=[
            {"type": "account_summary", "pages": [1]},
            {"type": "transactions", "pages": [2, 3]},
        ],
    )


VALID_DETECTION_JSON = json.dumps(
    {
        "transaction_regions": [
            {"page": 2, "region": [45, 180, 570, 730]},
            {"page": 3, "region": [45, 90, 570, 730]},
        ]
    }
)


def test_detect_valid_json_first_try() -> None:
    provider = _FakeProvider([VALID_DETECTION_JSON])
    service = TransactionRegionDetectionService(provider=provider)

    result = service.detect(_make_document(), _make_analysis())

    assert len(result.transaction_regions) == 2
    assert result.transaction_regions[0].page == 2
    assert result.transaction_regions[0].region == (45, 180, 570, 730)
    assert len(provider.calls) == 1


def test_detect_only_sends_transaction_flagged_pages() -> None:
    provider = _FakeProvider([VALID_DETECTION_JSON])
    service = TransactionRegionDetectionService(provider=provider)

    service.detect(_make_document(), _make_analysis())

    prompt_content = provider.calls[0][1]["content"]
    assert "Page 2" in prompt_content
    assert "Page 3" in prompt_content
    assert "Page 1" not in prompt_content


def test_detect_retries_after_invalid_then_succeeds() -> None:
    provider = _FakeProvider(["not json at all", VALID_DETECTION_JSON])
    service = TransactionRegionDetectionService(provider=provider)

    result = service.detect(_make_document(), _make_analysis())

    assert len(result.transaction_regions) == 2
    assert len(provider.calls) == 2
    second_call_messages = provider.calls[1]
    assert any(
        "wasn't valid" in m["content"] for m in second_call_messages if m["role"] == "user"
    )


def test_detect_raises_after_exhausting_attempts() -> None:
    provider = _FakeProvider(["not json", "still not json"])
    service = TransactionRegionDetectionService(provider=provider)

    with pytest.raises(TransactionRegionDetectionError):
        service.detect(_make_document(), _make_analysis())
