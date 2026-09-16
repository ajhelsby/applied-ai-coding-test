"""SQLAlchemy model for durable worker task-processing state."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.json import JsonValue
from app.infrastructure.persistence.models.base import Base


class TaskProcessingRecord(Base):
    """Database record used to claim and complete one deterministic worker task."""

    __tablename__ = "task_processing"

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_executions.execution_id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="claimed",
        server_default="claimed",
        index=True,
    )
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_data: Mapped[JsonValue] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completion_event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    completion_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


Index(
    "ix_task_processing_execution_id_node_id",
    TaskProcessingRecord.execution_id,
    TaskProcessingRecord.node_id,
)
