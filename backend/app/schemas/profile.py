from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ProfileRead(BaseModel):
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    currency: str | None = None
    profile_image: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    profile_image: str | None = Field(default=None, max_length=500)

    @field_validator("country", "currency")
    @classmethod
    def uppercase(cls, value: str | None) -> str | None:
        return value.upper() if value else value
