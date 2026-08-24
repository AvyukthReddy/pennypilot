import json

import pytest

from worker.document import Document, Page, TextBlock
from worker.transaction_regions import TransactionRegionDetection
from worker.transaction_schema_discovery import (
    TransactionSchemaDiscoveryError,
    TransactionSchemaDiscoveryService,
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


def _make_regions() -> TransactionRegionDetection:
    return TransactionRegionDetection(
        transaction_regions=[{"page": 2, "region": [45, 180, 570, 730]}]
    )


VALID_SCHEMA_JSON = json.dumps(
    {
        "transaction_fields": {
            "transaction_date": {"source": "column_1"},
            "description": {"source": "column_2"},
            "amount": [{"source": "column_3"}],
        }
    }
)

VALID_SPLIT_SCHEMA_JSON = json.dumps(
    {
        "transaction_fields": {
            "transaction_date": {"source": "column_1"},
            "post_date": {"source": "column_2"},
            "description": {"source": "column_3"},
            "amount": [
                {"source": "column_4", "semantics": "debit"},
                {"source": "column_5", "semantics": "credit"},
            ],
            "currency": {"source": "column_6"},
        }
    }
)


def test_discover_valid_json_first_try() -> None:
    provider = _FakeProvider([VALID_SCHEMA_JSON])
    service = TransactionSchemaDiscoveryService(provider=provider)

    result = service.discover(_make_document(), _make_regions())

    fields = result.transaction_fields
    assert fields.transaction_date.source == "column_1"
    assert fields.description.source == "column_2"
    assert len(fields.amount) == 1
    assert fields.amount[0].source == "column_3"
    assert len(provider.calls) == 1


def test_discover_handles_debit_credit_split_amount() -> None:
    provider = _FakeProvider([VALID_SPLIT_SCHEMA_JSON])
    service = TransactionSchemaDiscoveryService(provider=provider)

    result = service.discover(_make_document(), _make_regions())

    fields = result.transaction_fields
    assert len(fields.amount) == 2
    assert fields.amount[0].semantics == "debit"
    assert fields.amount[1].semantics == "credit"
    assert fields.post_date.source == "column_2"
    assert fields.currency.source == "column_6"


def test_discover_only_sends_blocks_inside_detected_region() -> None:
    provider = _FakeProvider([VALID_SCHEMA_JSON])
    service = TransactionSchemaDiscoveryService(provider=provider)

    service.discover(_make_document(), _make_regions())

    prompt_content = provider.calls[0][1]["content"]
    assert "Coffee" in prompt_content
    assert "STATEMENT HEADER" not in prompt_content


def test_discover_retries_after_invalid_then_succeeds() -> None:
    provider = _FakeProvider(["not json at all", VALID_SCHEMA_JSON])
    service = TransactionSchemaDiscoveryService(provider=provider)

    result = service.discover(_make_document(), _make_regions())

    assert result.transaction_fields.transaction_date.source == "column_1"
    assert len(provider.calls) == 2
    second_call_messages = provider.calls[1]
    assert any(
        "wasn't valid" in m["content"] for m in second_call_messages if m["role"] == "user"
    )


def test_discover_raises_after_exhausting_attempts() -> None:
    provider = _FakeProvider(["not json", "still not json"])
    service = TransactionSchemaDiscoveryService(provider=provider)

    with pytest.raises(TransactionSchemaDiscoveryError):
        service.discover(_make_document(), _make_regions())
