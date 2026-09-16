import uuid

from pydantic import BaseModel, Field


class MerchantRead(BaseModel):
    id: uuid.UUID
    name: str
    default_category_id: uuid.UUID | None
    default_subcategory_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class MerchantNormalizeRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
