import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), server_default="uploaded")
    parse_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    needs_ocr: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Which pipeline phase is currently running, only meaningful while
    # status == "processing"; left at its last value on success/failure so a
    # failed run still shows where it died. See worker/worker/tasks.py's
    # PROCESSING_STAGES for the fixed, ordered set of values.
    processing_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    processing_detail: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    document_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transaction_regions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transaction_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transaction_verification: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    financial_validation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # User-set override for the statement's currency, shown in place of
    # document_analysis's AI-detected currency when set. Null means "use the
    # detected value" (or the app-wide USD fallback if nothing was detected).
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # User-set override for the statement's institution, shown in place of
    # document_analysis's AI-detected institution when set. Null means "use
    # the detected value" (or nothing, if nothing was detected either).
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # User-set override for the statement's account-type tags (e.g.
    # ["checking", "savings"]), shown in place of the tags normalized from
    # document_analysis's AI-detected account_type when set. None means "use
    # the detected/normalized value"; an explicit [] means the user cleared
    # every tag and detection should NOT be used as a fallback.
    account_type_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
