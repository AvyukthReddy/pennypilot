import uuid
from datetime import datetime

from pydantic import BaseModel


class StatementRead(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    parse_error: str | None = None
    page_count: int | None = None
    needs_ocr: bool | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TextBlockRead(BaseModel):
    text: str
    x: float
    y: float
    width: float
    height: float


class ImageRegionRead(BaseModel):
    x: float
    y: float
    width: float
    height: float


class PageRead(BaseModel):
    page_number: int
    width: float
    height: float
    text: str
    text_blocks: list[TextBlockRead]
    images: list[ImageRegionRead]


class StatementPagesRead(BaseModel):
    statement_id: uuid.UUID
    pages: list[PageRead]
