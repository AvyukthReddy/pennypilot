import uuid

from pydantic import BaseModel, Field, field_validator


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        return " ".join(value.split())


class CategoryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        return " ".join(value.split())


class CategoryRead(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    is_default: bool
    sort_order: int
    # Only populated on top-level categories; subcategories omit this field.
    subcategories: list["CategoryRead"] | None = None

    model_config = {"from_attributes": True}


class CategoryReorderRequest(BaseModel):
    # All ids must be siblings (same parent_id, owned by the caller).
    parent_id: uuid.UUID | None = None
    ordered_ids: list[uuid.UUID]
