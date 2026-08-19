import json
import logging
import re

from pydantic import ValidationError

from worker.ai_provider import AIProvider
from worker.config import default_ai_provider_config
from worker.document import Document
from worker.document_analysis import DocumentAnalysis

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 1 initial + 1 self-repair retry

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class DocumentUnderstandingError(Exception):
    """The model never returned a DocumentAnalysis-shaped response within
    MAX_ATTEMPTS."""


def _strip_markdown_fence(text: str) -> str:
    return _FENCE_PATTERN.sub("", text).strip()


def _render_pages(document: Document) -> str:
    return "\n\n".join(
        f"=== Page {page.page_number} ===\n{page.text}" for page in document.pages
    )


def _system_prompt() -> str:
    schema = json.dumps(DocumentAnalysis.model_json_schema(), indent=2)
    return (
        "You are classifying a financial statement document. Given the text of "
        "each page, determine what kind of document it is and identify its "
        "sections.\n\n"
        "Respond with ONLY a single JSON object matching this schema — no "
        "markdown fences, no commentary, no extra text:\n\n"
        f"{schema}\n\n"
        'If a field can\'t be determined from the text, use null (or "unknown" '
        "for document_type). `sections` should cover the pages you were shown, "
        "grouped by what kind of content they contain."
    )


class DocumentUnderstandingService:
    """DocumentUnderstandingService.analyze(document) -> DocumentAnalysis.
    Answers "what is this document?" — not a transaction extraction. Best-effort:
    callers should treat a raised DocumentUnderstandingError (or any network
    failure from the underlying provider) as non-fatal to ingestion.

    Takes an AIProvider rather than constructing a model client itself — which
    provider/model actually runs is a config concern (worker.config), not
    something this pipeline should know or hard-code."""

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or AIProvider(default_ai_provider_config())

    def analyze(self, document: Document) -> DocumentAnalysis:
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _render_pages(document)},
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
                return DocumentAnalysis.model_validate_json(_strip_markdown_fence(reply))
            except ValidationError as exc:
                last_error = str(exc)
                logger.warning("document understanding: invalid response: %s", last_error)

        raise DocumentUnderstandingError(
            f"model never returned a valid DocumentAnalysis: {last_error}"
        )
