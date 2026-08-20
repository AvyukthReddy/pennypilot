import json
import logging

from pydantic import ValidationError

from worker._ai_json import strip_markdown_fence
from worker.ai_provider import AIProvider
from worker.config import default_ai_provider_config
from worker.document import Document, Page
from worker.document_analysis import DocumentAnalysis
from worker.transaction_regions import TransactionRegionDetection

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 1 initial + 1 self-repair retry


class TransactionRegionDetectionError(Exception):
    """The model never returned a TransactionRegionDetection-shaped response
    within MAX_ATTEMPTS."""


def _candidate_pages(document: Document, document_analysis: DocumentAnalysis) -> list[Page]:
    """Only the pages Phase 3 already flagged as "transactions" — the whole
    point of this step is narrowing further within that set, not redoing
    Phase 3's page-level classification."""
    transaction_page_numbers = {
        page_number
        for section in document_analysis.sections
        if section.type == "transactions"
        for page_number in section.pages
    }
    return [page for page in document.pages if page.page_number in transaction_page_numbers]


def _render_pages(pages: list[Page]) -> str:
    blocks = []
    for page in pages:
        lines = [f"=== Page {page.page_number} ({page.width:.0f}x{page.height:.0f}) ==="]
        for block in page.text_blocks:
            x0, y0 = block.x, block.y
            x1, y1 = block.x + block.width, block.y + block.height
            lines.append(f"[{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}] {block.text!r}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _system_prompt() -> str:
    schema = json.dumps(TransactionRegionDetection.model_json_schema(), indent=2)
    return (
        "You are given the positioned text blocks for one or more pages of a "
        "financial statement, already known to contain transaction line items "
        "somewhere on the page. Each block is shown as "
        "[x0, y0, x1, y1] \"text\", in points from the page's top-left corner.\n\n"
        "For each page, find the single bounding region that contains the "
        "transaction table itself — excluding page headers, footers, logos, "
        "and margins. Use the same coordinate space you were given.\n\n"
        "Respond with ONLY a single JSON object matching this schema — no "
        "markdown fences, no commentary, no extra text:\n\n"
        f"{schema}\n\n"
        "Include exactly one region per page you were shown."
    )


class TransactionRegionDetectionService:
    """TransactionRegionDetectionService.detect(document, document_analysis) ->
    TransactionRegionDetection. Narrows Phase 3's page-level "transactions"
    sections down to an exact bounding region per page — the reduction step
    before real line-item extraction. Best-effort: callers should treat a
    raised TransactionRegionDetectionError (or any network failure from the
    underlying provider) as non-fatal to ingestion.

    Takes an AIProvider rather than constructing a model client itself, same
    as DocumentUnderstandingService — provider/model is a config concern."""

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or AIProvider(default_ai_provider_config())

    def detect(
        self, document: Document, document_analysis: DocumentAnalysis
    ) -> TransactionRegionDetection:
        pages = _candidate_pages(document, document_analysis)
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _render_pages(pages)},
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
                return TransactionRegionDetection.model_validate_json(
                    strip_markdown_fence(reply)
                )
            except ValidationError as exc:
                last_error = str(exc)
                logger.warning(
                    "transaction region detection: invalid response: %s", last_error
                )

        raise TransactionRegionDetectionError(
            f"model never returned a valid TransactionRegionDetection: {last_error}"
        )
