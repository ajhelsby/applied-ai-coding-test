"""SQLAlchemy models for durable task retry state."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.json import JsonValue
from app.infrastructure.persistence.models.base import Base


class LogicalTaskRecord(Base):
    """Durable state shared by every attempt of one logical task."""

    __tablename__ = "logical_tasks"

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_executions.execution_id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    handler: Mapped[str] = mapped_column(String(255), nullable=False)
    handler_config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resolved_input: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    final_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskAttemptRecord(Base):
    """Durable history and status for one uniquely identified attempt."""

    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_number", name="uq_task_attempts_task_number"),
        UniqueConstraint("failure_event_id", name="uq_task_attempts_failure_event_id"),
        Index("ix_task_attempts_task_id_status", "task_id", "status"),
    )

    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("logical_tasks.task_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    completion_event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_data: Mapped[JsonValue] = mapped_column(JSONB, nullable=True)
    completion_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskRetryDispatchRecord(Base):
    """Durable delayed-publication state for a retry attempt."""

    __tablename__ = "task_retry_dispatches"
    __table_args__ = (Index("ix_task_retry_dispatches_due", "status", "available_at"),)

    attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("task_attempts.attempt_id", ondelete="CASCADE"),
        primary_key=True,
    )
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
