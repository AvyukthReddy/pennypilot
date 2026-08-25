import re

# Small open models commonly wrap JSON replies in a ```json fence despite being
# told not to, shared by every AI service that needs to parse a JSON reply.
_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def strip_markdown_fence(text: str) -> str:
    return _FENCE_PATTERN.sub("", text).strip()
