import io

from PIL import Image

from worker._regions import _blocks_in_region, _image_for_region
from worker.document import Page, TextBlock
from worker.pdf_analysis import PAGE_IMAGE_RESOLUTION

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


def _make_page_image(width_pt: float, height_pt: float) -> bytes:
    scale = PAGE_IMAGE_RESOLUTION / 72
    img = Image.new("RGB", (round(width_pt * scale), round(height_pt * scale)), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_image_for_region_crops_to_pixel_bbox() -> None:
    region = (45, 180, 570, 730)
    page = Page(
        page_number=1,
        width=612,
        height=792,
        text="",
        text_blocks=[],
        images=[],
        image=_make_page_image(612, 792),
    )

    cropped_bytes = _image_for_region(page, region)

    assert cropped_bytes is not None
    scale = PAGE_IMAGE_RESOLUTION / 72
    x0, y0, x1, y1 = (round(coord * scale) for coord in region)
    with Image.open(io.BytesIO(cropped_bytes)) as cropped:
        assert cropped.size == (x1 - x0, y1 - y0)


def test_image_for_region_returns_none_without_page_image() -> None:
    page = Page(
        page_number=1,
        width=612,
        height=792,
        text="",
        text_blocks=[],
        images=[],
        image=None,
    )

    assert _image_for_region(page, (45, 180, 570, 730)) is None
