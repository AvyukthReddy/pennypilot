import json
import logging

from pydantic import ValidationError

from worker._ai_json import strip_markdown_fence
from worker._regions import _blocks_in_region
from worker.ai_provider import AIProvider
from worker.config import default_ai_provider_config
from worker.document import Document
from worker.extracted_transactions import TransactionExtraction
from worker.transaction_regions import TransactionRegion
from worker.transaction_schema import TransactionFields

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 1 initial + 1 self-repair retry


class TransactionExtractionError(Exception):
    """The model never returned a TransactionExtraction-shaped response
    within MAX_ATTEMPTS."""


def _render_region(document: Document, region: TransactionRegion) -> str:
    pages_by_number = {page.page_number: page for page in document.pages}
    page = pages_by_number.get(region.page)
    if page is None:
        return ""
    lines = [f"=== Page {region.page} ==="]
    for block in _blocks_in_region(page, region.region):
        x0, y0 = block.x, block.y
        x1, y1 = block.x + block.width, block.y + block.height
        lines.append(f"[{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}] {block.text!r}")
    return "\n".join(lines)


def _system_prompt(transaction_fields: TransactionFields) -> str:
    schema = json.dumps(TransactionExtraction.model_json_schema(), indent=2)
    fields = transaction_fields.model_dump_json(indent=2)
    return (
        "You are given the positioned text blocks inside one page's "
        "transaction table region of a financial statement. Each block is "
        "shown as [x0, y0, x1, y1] \"text\", in points from the page's "
        "top-left corner.\n\n"
        "This document's column layout was already discovered — here is the "
        "mapping from target fields to this document's actual columns "
        "(column_N labels refer to left-to-right x-position, and an "
        "amount-bearing column may carry semantics \"debit\" or \"credit\" "
        "when the table splits amount across two columns):\n\n"
        f"{fields}\n\n"
        "Using that mapping, extract EVERY transaction row present in the "
        "blocks below — not a sample, all of them. For a debit/credit-split "
        "amount, combine the two columns into a single signed amount per row "
        "(debit negative, credit positive) unless the column's own text "
        "already carries a sign. Only emit the fields transaction_date, "
        "post_date, description, amount, and currency — do NOT invent a "
        "category, do NOT add commentary or explanation, no prose, just the "
        "transactions.\n\n"
        "This is the JSON Schema your response must conform to — it "
        "describes the shape of the answer, it is NOT the answer itself. "
        "Respond with ONLY a JSON object that is a valid *instance* of this "
        "schema (actual values, not the schema's own \"$defs\"/\"properties\""
        "/\"type\" keywords), no markdown fences, no commentary, no extra "
        "text:\n\n"
        f"{schema}"
    )


class TransactionExtractionService:
    """TransactionExtractionService.extract(document, region, transaction_fields)
    -> TransactionExtraction. Called once per detected transaction region
    (i.e. once per flagged page), not once per document — each region's rows
    are extracted independently using the column mapping Phase 5 already
    discovered. Best-effort: callers should treat a raised
    TransactionExtractionError (or any network failure from the underlying
    provider) as non-fatal, and should keep whatever other regions already
    succeeded.

    Takes an AIProvider rather than constructing a model client itself, same
    as the other AI services — provider/model is a config concern."""

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or AIProvider(default_ai_provider_config())

    def extract(
        self,
        document: Document,
        region: TransactionRegion,
        transaction_fields: TransactionFields,
    ) -> TransactionExtraction:
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt(transaction_fields)},
            {"role": "user", "content": _render_region(document, region)},
        ]

        last_error: str | None = None
        for _ in range(MAX_ATTEMPTS):
            if last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"That response wasn't valid: {last_error}. Respond "
                            "again with ONLY the corrected JSON object."
                        ),
                    }
                )

            reply = self.provider.complete(messages)
            messages.append({"role": "assistant", "content": reply})

            try:
                return TransactionExtraction.model_validate_json(strip_markdown_fence(reply))
            except ValidationError as exc:
                last_error = str(exc)
                logger.warning("transaction extraction: invalid response: %s", last_error)

        raise TransactionExtractionError(
            f"model never returned a valid TransactionExtraction: {last_error}"
        )
