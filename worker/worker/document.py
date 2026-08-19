from dataclasses import dataclass


@dataclass
class Document:
    """The ingested-and-ready-for-parsing unit a future parser will consume.
    Built once ingestion succeeds. Nothing reads it yet — this is the
    explicit handoff contract for the parser that doesn't exist yet."""

    statement_id: str
    filename: str
    content_type: str
    data: bytes
    file_hash: str
    size_bytes: int
    page_count: int | None
    parser_version: str
