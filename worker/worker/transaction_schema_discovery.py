import json
import logging

from pydantic import ValidationError

from worker._ai_json import strip_markdown_fence
from worker.ai_provider import AIProvider
from worker.config import default_ai_provider_config
from worker.document import Document, Page, TextBlock
from worker.transaction_regions import TransactionRegionDetection
from worker.transaction_schema import TransactionSchemaDiscovery

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 1 initial + 1 self-repair retry


class TransactionSchemaDiscoveryError(Exception):
    """The model never returned a TransactionSchemaDiscovery-shaped response
    within MAX_ATTEMPTS."""


def _blocks_in_region(page: Page, region: tuple[float, float, float, float]) -> list[TextBlock]:
    """Crops a page's text_blocks down to the ones actually inside its
    detected transaction region (Phase 4) — a center-point test, not strict
    containment, so a block that slightly straddles the boundary isn't
    dropped. This is what makes schema discovery see just the table, not
    whatever headers/footers/margins Phase 4 already excluded."""
    x0, y0, x1, y1 = region
    return [
        block
        for block in page.text_blocks
        if x0 <= block.x + block.width / 2 <= x1 and y0 <= block.y + block.height / 2 <= y1
    ]


def _render_regions(document: Document, transaction_regions: TransactionRegionDetection) -> str:
    pages_by_number = {page.page_number: page for page in document.pages}
    rendered: list[str] = []
    for region in transaction_regions.transaction_regions:
        page = pages_by_number.get(region.page)
        if page is None:
            continue
        lines = [f"=== Page {region.page} ==="]
        for block in _blocks_in_region(page, region.region):
            x0, y0 = block.x, block.y
            x1, y1 = block.x + block.width, block.y + block.height
            lines.append(f"[{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}] {block.text!r}")
        rendered.append("\n".join(lines))
    return "\n\n".join(rendered)


def _system_prompt() -> str:
    schema = json.dumps(TransactionSchemaDiscovery.model_json_schema(), indent=2)
    return (
        "You are given the positioned text blocks inside the transaction table "
        "region of one or more pages of a financial statement. Each block is "
        "shown as [x0, y0, x1, y1] \"text\", in points from the page's "
        "top-left corner.\n\n"
        "Figure out what a transaction record looks like in THIS document — "
        "table layouts vary wildly between banks (e.g. \"Date | Description | "
        "Amount\", or \"Transaction Date | Posting Date | Description | Debit "
        "| Credit | Balance\", or something else entirely). Identify the "
        "distinct columns by their x-position and label them column_1, "
        "column_2, ... left to right. Then map those columns onto these "
        "target fields: transaction_date (required), post_date (optional, "
        "only if a separate posting date column exists), description "
        "(required), amount (required — a list, because some tables split "
        "amount across separate Debit/Credit columns: give one entry per "
        "amount-bearing column, tagging each with semantics \"debit\" or "
        "\"credit\" when split, or a single entry with no semantics tag when "
        "there's just one signed amount column), and currency (optional, only "
        "if a currency column exists — omit it if currency is only "
        "mentioned elsewhere, not as its own column).\n\n"
        "This is the JSON Schema your response must conform to — it describes "
        "the shape of the answer, it is NOT the answer itself. Respond with "
        "ONLY a JSON object that is a valid *instance* of this schema (actual "
        "values, not the schema's own \"$defs\"/\"properties\"/\"type\" "
        "keywords), no markdown fences, no commentary, no extra text:\n\n"
        f"{schema}"
    )


class TransactionSchemaDiscoveryService:
    """TransactionSchemaDiscoveryService.discover(document, transaction_regions)
    -> TransactionSchemaDiscovery. Answers "what does a transaction look like
    in this document?" — maps this document's actual table columns onto
    Transaction's fixed fields, format-agnostically. Not an extraction of any
    row's data. Best-effort: callers should treat a raised
    TransactionSchemaDiscoveryError (or any network failure from the
    underlying provider) as non-fatal to ingestion.

    Takes an AIProvider rather than constructing a model client itself, same
    as the other AI services — provider/model is a config concern."""

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or AIProvider(default_ai_provider_config())

    def discover(
        self, document: Document, transaction_regions: TransactionRegionDetection
    ) -> TransactionSchemaDiscovery:
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _render_regions(document, transaction_regions)},
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
                return TransactionSchemaDiscovery.model_validate_json(
                    strip_markdown_fence(reply)
                )
            except ValidationError as exc:
                last_error = str(exc)
                logger.warning(
                    "transaction schema discovery: invalid response: %s", last_error
                )

        raise TransactionSchemaDiscoveryError(
            f"model never returned a valid TransactionSchemaDiscovery: {last_error}"
        )
