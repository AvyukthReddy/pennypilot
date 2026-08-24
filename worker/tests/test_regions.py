from worker._regions import _blocks_in_region
from worker.document import Page, TextBlock

HEADER_BLOCK = TextBlock(text="STATEMENT HEADER", x=45, y=20, width=200, height=12)
ROW_BLOCK = TextBlock(text="07/14/2026 Coffee $5.75", x=45, y=200, width=300, height=12)


def test_blocks_in_region_crops_to_center_point() -> None:
    page = Page(
        page_number=1,
        width=612,
        height=792,
        text="",
        text_blocks=[HEADER_BLOCK, ROW_BLOCK],
        images=[],
    )

    result = _blocks_in_region(page, (45, 180, 570, 730))

    assert result == [ROW_BLOCK]
