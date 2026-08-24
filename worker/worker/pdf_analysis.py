import io
import logging

import pdfplumber

from worker.document import ImageRegion, Page, TextBlock

logger = logging.getLogger(__name__)

# Below this average characters-per-page, treat the PDF as scanned/image-only
# rather than text-based. Real statements clear this by 10-100x; a truly
# blank or image-only page won't.
SCANNED_TEXT_THRESHOLD = 20

# DPI used to rasterize each page for AI services that benefit from seeing
# the actual visual layout (transaction region detection, extraction) — not
# persisted anywhere, so this is purely an inference-time resolution choice.
PAGE_IMAGE_RESOLUTION = 100


def analyze_pdf(data: bytes) -> list[Page]:
    """Inspects a PDF's text layer and layout. Raises if the PDF can't be
    opened (corrupt/unreadable) — callers already handle that broadly."""
    pages: list[Page] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text_blocks = [
                TextBlock(
                    text=line["text"],
                    x=line["x0"],
                    y=line["top"],
                    width=line["x1"] - line["x0"],
                    height=line["bottom"] - line["top"],
                )
                for line in page.extract_text_lines(strip=True, return_chars=False)
            ]
            images = [
                ImageRegion(
                    x=image["x0"],
                    y=image["top"],
                    width=image["x1"] - image["x0"],
                    height=image["bottom"] - image["top"],
                )
                for image in page.images
            ]
            rendered_image: bytes | None = None
            try:
                buf = io.BytesIO()
                page.to_image(resolution=PAGE_IMAGE_RESOLUTION).original.save(buf, format="PNG")
                rendered_image = buf.getvalue()
            except Exception:
                logger.warning("page %d: failed to render page image", index, exc_info=True)

            pages.append(
                Page(
                    page_number=index,
                    width=page.width,
                    height=page.height,
                    text=page.extract_text() or "",
                    text_blocks=text_blocks,
                    images=images,
                    image=rendered_image,
                )
            )
    return pages


def is_scanned(pages: list[Page]) -> bool:
    """True when a PDF has (near-)no extractable text layer — a scanned or
    image-only document that a future OCR/vision pass would need to read."""
    if not pages:
        return False
    total_chars = sum(len(page.text) for page in pages)
    return (total_chars / len(pages)) < SCANNED_TEXT_THRESHOLD
