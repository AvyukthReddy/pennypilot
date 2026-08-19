import io

from pypdf import PdfReader


def count_pdf_pages(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)
