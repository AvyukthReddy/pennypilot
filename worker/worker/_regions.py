import io

from PIL import Image

from worker.document import Page, TextBlock
from worker.pdf_analysis import PAGE_IMAGE_RESOLUTION


def _blocks_in_region(page: Page, region: tuple[float, float, float, float]) -> list[TextBlock]:
    """Crops a page's text_blocks down to the ones actually inside a detected
    transaction region (Phase 4) — a center-point test, not strict
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
