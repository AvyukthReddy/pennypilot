from dataclasses import dataclass


@dataclass
class TextBlock:
    """A line of text on a page, with its position in PDF points from the
    page's top-left corner."""

    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class ImageRegion:
    """An embedded image's position on a page. Bounding box only, nothing
    consumes pixel data yet, so bytes aren't extracted."""

    x: float
    y: float
    width: float
    height: float


@dataclass
class Page:
    page_number: int
    width: float
    height: float
    text: str
    text_blocks: list[TextBlock]
    images: list[ImageRegion]
    # A rendered raster (PNG) of the whole page, at PAGE_IMAGE_RESOLUTION (see
    # pdf_analysis.py), None if rendering failed for this page. Kept
    # in-memory only; never persisted to Statement.pages.
    image: bytes | None = None


@dataclass
class Document:
    """The ingested-and-ready-for-parsing unit a future parser will consume.
    Built once ingestion succeeds. Nothing reads it yet, this is the
    explicit handoff contract for the parser that doesn't exist yet."""

    statement_id: str
    filename: str
    content_type: str
    data: bytes
    file_hash: str
    size_bytes: int
    page_count: int | None
    parser_version: str
    pages: list[Page]
    needs_ocr: bool
