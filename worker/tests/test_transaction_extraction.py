import io
import json
from decimal import Decimal

import pytest
from PIL import Image

from worker.document import Document, Page, TextBlock
from worker.extracted_transactions import TransactionExtraction
from worker.pdf_analysis import PAGE_IMAGE_RESOLUTION
from worker.transaction_extraction import (
    TransactionExtractionError,
    TransactionExtractionService,
)
from worker.transaction_regions import TransactionRegion
from worker.transaction_schema import TransactionFields
from worker.verification_issues import VerificationIssue


def _make_page_image(width_pt: float, height_pt: float) -> bytes:
    scale = PAGE_IMAGE_RESOLUTION / 72
    img = Image.new("RGB", (round(width_pt * scale), round(height_pt * scale)), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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


def _make_fields() -> TransactionFields:
    return TransactionFields(
        transaction_date={"source": "column_1"},
        description={"source": "column_2"},
        amount=[{"source": "column_3"}],
    )


VALID_EXTRACTION_JSON = json.dumps(
    {
        "transactions": [
            {
                "transaction_date": "2026-07-14",
                "post_date": None,
                "description": "STARBUCKS #2938 AUSTIN TX",
                "amount": -7.42,
                "currency": "USD",
            },
            {
                "transaction_date": "2026-07-15",
                "post_date": None,
                "description": "UBER TRIP",
                "amount": -18.63,
                "currency": "USD",
            },
        ]
    }
)


def test_extract_valid_json_first_try() -> None:
    provider = _FakeProvider([VALID_EXTRACTION_JSON])
    service = TransactionExtractionService(provider=provider)

    result = service.extract(_make_document(), _make_region(), _make_fields())

    assert len(result.transactions) == 2
    first = result.transactions[0]
    assert first.description == "STARBUCKS #2938 AUSTIN TX"
    assert first.amount == Decimal("-7.42")
    assert first.currency == "USD"
    assert first.post_date is None
    assert len(provider.calls) == 1


def test_extract_prompt_includes_field_mapping_and_only_region_blocks() -> None:
    provider = _FakeProvider([VALID_EXTRACTION_JSON])
    service = TransactionExtractionService(provider=provider)

    service.extract(_make_document(), _make_region(), _make_fields())

    system_content = provider.calls[0][0]["content"]
    user_content = provider.calls[0][1]["content"]
    user_text = next(part["text"] for part in user_content if part["type"] == "text")
    assert "column_1" in system_content
    assert "column_3" in system_content
    assert "Coffee" in user_text
    assert "STATEMENT HEADER" not in user_text
    assert not any(part["type"] == "image_url" for part in user_content)


def test_extract_includes_cropped_region_image_when_available() -> None:
    document = _make_document()
    document.pages[0].image = _make_page_image(document.pages[0].width, document.pages[0].height)
    provider = _FakeProvider([VALID_EXTRACTION_JSON])
    service = TransactionExtractionService(provider=provider)

    service.extract(document, _make_region(), _make_fields())

    user_content = provider.calls[0][1]["content"]
    assert any(part["type"] == "image_url" for part in user_content)


def test_extract_with_correction_appends_previous_attempt_and_issues() -> None:
    provider = _FakeProvider([VALID_EXTRACTION_JSON])
    service = TransactionExtractionService(provider=provider)
    previous = TransactionExtraction.model_validate_json(VALID_EXTRACTION_JSON)
    issues = [
        VerificationIssue(type="wrong_amount", page=2, description="UBER TRIP amount should be -18.65"),
    ]

    service.extract(
        _make_document(),
        _make_region(),
        _make_fields(),
        previous_attempt=previous,
        verification_issues=issues,
    )

    messages = provider.calls[0]
    assert messages[2]["role"] == "assistant"
    assert "UBER TRIP" in messages[2]["content"]
    assert messages[3]["role"] == "user"
    assert "wrong_amount" in messages[3]["content"]
    assert "fixing every issue" in messages[3]["content"]


def test_extract_with_recovery_hint_and_previous_attempt() -> None:
    provider = _FakeProvider([VALID_EXTRACTION_JSON])
    service = TransactionExtractionService(provider=provider)
    previous = TransactionExtraction.model_validate_json(VALID_EXTRACTION_JSON)

    service.extract(
        _make_document(),
        _make_region(),
        _make_fields(),
        previous_attempt=previous,
        recovery_hint="Expected ending balance 1330.00, statement shows 1380.00",
    )

    messages = provider.calls[0]
    assert messages[2]["role"] == "assistant"
    assert "UBER TRIP" in messages[2]["content"]
    assert messages[3]["role"] == "user"
    assert "financial reconciliation check" in messages[3]["content"]
    assert "1330.00" in messages[3]["content"]


def test_extract_with_recovery_hint_and_no_previous_attempt() -> None:
    provider = _FakeProvider([VALID_EXTRACTION_JSON])
    service = TransactionExtractionService(provider=provider)

    service.extract(
        _make_document(),
        _make_region(),
        _make_fields(),
        recovery_hint="Expected ending balance 1330.00, statement shows 1380.00",
    )

    messages = provider.calls[0]
    # No previous attempt ⇒ no extra assistant message; the recovery-hint
    # message is appended directly after the region content.
    assert messages[2]["role"] == "user"
    assert "financial reconciliation check" in messages[2]["content"]


def test_extract_retries_after_invalid_then_succeeds() -> None:
    provider = _FakeProvider(["not json at all", VALID_EXTRACTION_JSON])
    service = TransactionExtractionService(provider=provider)

    result = service.extract(_make_document(), _make_region(), _make_fields())

    assert len(result.transactions) == 2
    assert len(provider.calls) == 2
    second_call_messages = provider.calls[1]
    assert any(
        "wasn't valid" in m["content"] for m in second_call_messages if m["role"] == "user"
    )


def test_extract_raises_after_exhausting_attempts() -> None:
    provider = _FakeProvider(["not json", "still not json"])
    service = TransactionExtractionService(provider=provider)

    with pytest.raises(TransactionExtractionError):
        service.extract(_make_document(), _make_region(), _make_fields())
