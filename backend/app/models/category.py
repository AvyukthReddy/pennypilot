import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), index=True
    )
    # NULL for a top-level category; otherwise points at a top-level category's
    # id. Only two levels are supported, enforced in app/api/categories.py
    # rather than by a check constraint.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100))
    # True for categories seeded from the default taxonomy on first fetch.
    # Defaults are ordinary rows after seeding: users can rename/delete them
    # like any other category, this flag is informational only.
    is_default: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
