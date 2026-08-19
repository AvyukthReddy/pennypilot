# AUTHORITATIVE SCHEMA LIVES IN backend/app/models/*.py, MIGRATED VIA ALEMBIC.
# This file is NOT authoritative. It is a hand-maintained, read/write mapping
# onto the same Postgres tables, kept intentionally separate from the backend
# package so the two services don't share a dependency. Any column added,
# renamed, or removed in backend/app/models/statement.py or transaction.py
# MUST be mirrored here by hand, or the worker will silently drift out of
# sync with the real schema.
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from worker.db import Base


class StatementRow(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    parse_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    needs_ocr: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    document_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class TransactionRow(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    transaction_date: Mapped[date] = mapped_column(Date)
    post_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    raw_row: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
