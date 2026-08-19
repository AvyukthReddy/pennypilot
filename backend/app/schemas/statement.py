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
    created_at: datetime

    model_config = {"from_attributes": True}
