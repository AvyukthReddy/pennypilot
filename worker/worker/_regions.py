import io

from PIL import Image

from worker._multimodal import image_part, text_part
from worker.document import Document, Page, TextBlock
from worker.pdf_analysis import PAGE_IMAGE_RESOLUTION
from worker.transaction_regions import TransactionRegion


def _blocks_in_region(page: Page, region: tuple[float, float, float, float]) -> list[TextBlock]:
    """Crops a page's text_blocks down to the ones actually inside a detected
    transaction region (Phase 4), a center-point test, not strict
    containment, so a block that slightly straddles the boundary isn't
    dropped. Shared by every AI service that needs to see just a region's
    content (schema discovery, extraction), not whatever headers/footers/
    margins Phase 4 already excluded."""
    x0, y0, x1, y1 = region
    return [
        block
        for block in page.text_blocks
        if x0 <= block.x + block.width / 2 <= x1 and y0 <= block.y + block.height / 2 <= y1
    ]


def _image_for_region(page: Page, region: tuple[float, float, float, float]) -> bytes | None:
    """Crops a page's rendered image down to a detected region's bounding
    box, converting from PDF points (the region's own coordinate space) to
    the pixel space page.image was rendered at. None when the page has no
    rendered image (rendering failed for it, or it was never populated)."""
    if page.image is None:
        return None
    scale = PAGE_IMAGE_RESOLUTION / 72
    pixel_box = tuple(round(coord * scale) for coord in region)
    with Image.open(io.BytesIO(page.image)) as img:
        cropped = img.crop(pixel_box)
        out = io.BytesIO()
        cropped.save(out, format="PNG")
        return out.getvalue()


def _region_content(document: Document, region: TransactionRegion) -> list[dict]:
    """Builds the text-part-plus-optional-image-part content for a single
    detected region, the coordinate-tagged text blocks inside it, plus
    (when available) the region cropped out of that page's rendered image.
    Shared by every AI service that operates on one region at a time
    (extraction, verification)."""
    pages_by_number = {page.page_number: page for page in document.pages}
    page = pages_by_number.get(region.page)
    if page is None:
        return [text_part("")]
    lines = [f"=== Page {region.page} ==="]
    for block in _blocks_in_region(page, region.region):
        x0, y0 = block.x, block.y
        x1, y1 = block.x + block.width, block.y + block.height
        lines.append(f"[{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}] {block.text!r}")
    content: list[dict] = [text_part("\n".join(lines))]
    image = _image_for_region(page, region.region)
    if image is not None:
        content.append(image_part(image))
    return content
