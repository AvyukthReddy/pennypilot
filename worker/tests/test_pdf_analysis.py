import io

import pytest
from reportlab.pdfgen import canvas

from worker.pdf_analysis import analyze_pdf, is_scanned


def _make_text_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.drawString(145, 480, "STARBUCKS")
    c.drawString(72, 460, "07/14/2026    Coffee and pastries    $5.75")
    c.drawString(72, 440, "07/15/2026    Monthly subscription   $12.99")
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_blank_pdf(pages: int = 2) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    for _ in range(pages):
        c.showPage()
    c.save()
    return buf.getvalue()


def test_analyze_pdf_extracts_page_shape_and_text_blocks() -> None:
    pages = analyze_pdf(_make_text_pdf())

    assert len(pages) == 1
    page = pages[0]
    assert page.page_number == 1
    assert page.width == 612
    assert page.height == 792
    assert "STARBUCKS" in page.text
    assert len(page.text_blocks) == 3

    block = page.text_blocks[0]
    assert block.text == "STARBUCKS"
    assert block.x == pytest.approx(145, abs=1)
    # drawString's baseline is at y=480 (measured from the page bottom);
    # pdfplumber's "top" is measured from the page top, so ~792-480=312,
    # nudged down for line ascent, allow a wide tolerance for font metrics.
    assert block.y == pytest.approx(302, abs=15)
    assert block.width > 0
    assert block.height > 0

    assert not is_scanned(pages)


def test_analyze_pdf_renders_page_image() -> None:
    pages = analyze_pdf(_make_text_pdf())

    page = pages[0]
    assert page.image is not None
    assert page.image[:8] == b"\x89PNG\r\n\x1a\n"


def test_analyze_pdf_blank_pages_flagged_as_scanned() -> None:
    pages = analyze_pdf(_make_blank_pdf(pages=2))

    assert len(pages) == 2
    for page in pages:
        assert page.text_blocks == []
        assert page.text == ""

    assert is_scanned(pages)


def test_analyze_pdf_corrupt_bytes_raises() -> None:
    with pytest.raises(Exception):
        analyze_pdf(b"this is not a real pdf file")
