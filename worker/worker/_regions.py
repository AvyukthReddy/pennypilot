from worker.document import Page, TextBlock


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
