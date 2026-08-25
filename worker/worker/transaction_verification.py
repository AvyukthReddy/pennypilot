import json
import logging

from pydantic import ValidationError

from worker._ai_json import strip_markdown_fence
from worker._multimodal import text_part
from worker._regions import _region_content
from worker.ai_provider import AIProvider
from worker.config import default_ai_provider_config
from worker.document import Document
from worker.extracted_transactions import TransactionExtraction
from worker.transaction_regions import TransactionRegion
from worker.verification_issues import TransactionVerification

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 1 initial + 1 self-repair retry


class TransactionVerificationError(Exception):
    """The model never returned a TransactionVerification-shaped response
    within MAX_ATTEMPTS."""


def _system_prompt() -> str:
    schema = json.dumps(TransactionVerification.model_json_schema(), indent=2)
    return (
        "You are given a transaction table region (positioned text blocks, "
        "and possibly a rendered image, from one page of a financial "
        "statement) plus a list of transactions an earlier extraction pass "
        "produced from that exact region. Check the extraction against the "
        "region for:\n"
        "1. any transactions missing from the extraction\n"
        "2. any transactions duplicated in the extraction\n"
        "3. wrong dates\n"
        "4. wrong amounts\n"
        "5. wrong debit/credit signs\n"
        "6. multi-line transactions that were incorrectly split into two "
        "rows or merged into one\n\n"
        "This is the JSON Schema your response must conform to, it "
        "describes the shape of the answer, it is NOT the answer itself. "
        "Respond with ONLY a JSON object that is a valid *instance* of this "
        "schema (actual values, not the schema's own \"$defs\"/\"properties\""
        "/\"type\" keywords), no markdown fences, no commentary, no extra "
        "text. If nothing is wrong, respond with valid=true and an empty "
        "issues list:\n\n"
        f"{schema}"
    )


class TransactionVerificationService:
    """TransactionVerificationService.verify(document, region, extraction)
    -> TransactionVerification. Checks one region's already-extracted
    transactions against that same region's content, catching what
    TransactionExtractionService may have gotten wrong (missing/duplicate
    rows, wrong dates/amounts/signs, split-or-merged multi-line rows).
    Best-effort: callers should treat a raised TransactionVerificationError
    (or any network failure from the underlying provider) as non-fatal,
    a failed verification just means the original extraction is used as-is,
    uncorrected.

    Takes an AIProvider rather than constructing a model client itself, same
    as the other AI services, provider/model is a config concern."""

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or AIProvider(default_ai_provider_config())

    def verify(
        self,
        document: Document,
        region: TransactionRegion,
        extraction: TransactionExtraction,
    ) -> TransactionVerification:
        content = _region_content(document, region)
        content.append(text_part(f"Extracted transactions:\n{extraction.model_dump_json(indent=2)}"))
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": content},
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
                return TransactionVerification.model_validate_json(strip_markdown_fence(reply))
            except ValidationError as exc:
                last_error = str(exc)
                logger.warning("transaction verification: invalid response: %s", last_error)

        raise TransactionVerificationError(
            f"model never returned a valid TransactionVerification: {last_error}"
        )
