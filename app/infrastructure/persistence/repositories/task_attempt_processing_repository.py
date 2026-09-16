"""SQLAlchemy worker processing state keyed by attempt ID."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.json import JsonValue
from app.domain.repositories.task_attempt_processing_repository import (
    TaskAttemptProcessingRepository,
)
from app.domain.repositories.task_processing_repository import (
    TaskClaimOutcome,
    TaskProcessingResult,
)
from app.infrastructure.persistence.models.task_retry import LogicalTaskRecord, TaskAttemptRecord


class SqlAlchemyTaskAttemptProcessingRepository(TaskAttemptProcessingRepository):
    """Attempt-level worker idempotency backed by PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_attempt(
        self,
        attempt_id: UUID,
        task_id: str,
        execution_id: UUID,
        node_id: str,
        worker_id: str,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> TaskClaimOutcome:
        result = await self._session.execute(
            select(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .with_for_update()
        )
        attempt = result.scalar_one_or_none()
        if attempt is None:
            raise ValueError(f"Attempt '{attempt_id}' was not found.")
        logical_result = await self._session.execute(
            select(LogicalTaskRecord).where(LogicalTaskRecord.task_id == task_id)
        )
        logical_task = logical_result.scalar_one_or_none()
        if (
            logical_task is None
            or attempt.task_id != task_id
            or logical_task.execution_id != execution_id
            or logical_task.node_id != node_id
        ):
            raise ValueError(f"Attempt '{attempt_id}' does not match task '{task_id}'.")
        if attempt.status == "completed":
            return TaskClaimOutcome.ALREADY_COMPLETED
        if attempt.status == "result_recorded":
            return TaskClaimOutcome.RESULT_RECORDED
        if attempt.claimed_by is not None and (
            attempt.claim_expires_at is None or attempt.claim_expires_at > claimed_at
        ):
            return TaskClaimOutcome.CURRENTLY_CLAIMED
        await self._session.execute(
            update(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .values(
                status="claimed",
                claimed_by=worker_id,
                claimed_at=claimed_at,
                claim_expires_at=claim_expires_at,
                updated_at=claimed_at,
            )
        )
        return TaskClaimOutcome.CLAIMED

    async def record_result(
        self,
        attempt_id: UUID,
        event_id: UUID,
        result_data: JsonValue,
        error_message: str | None,
        error_type: str | None,
    ) -> None:
        result = await self._session.execute(
            update(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .where(TaskAttemptRecord.status == "claimed")
            .values(
                status="result_recorded",
                result_data=result_data,
                error_message=error_message,
                error_type=error_type,
                completion_event_id=event_id,
            )
            .returning(TaskAttemptRecord.attempt_id)
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"Attempt '{attempt_id}' is not available to record a result.")

    async def get_result(self, attempt_id: UUID) -> TaskProcessingResult:
        result = await self._session.execute(
            select(TaskAttemptRecord).where(TaskAttemptRecord.attempt_id == attempt_id)
        )
        attempt = result.scalar_one()
        if attempt.completion_event_id is None:
            raise ValueError(f"Attempt '{attempt_id}' has no completion event to replay.")
        return TaskProcessingResult(
            event_id=attempt.completion_event_id,
            result_data=attempt.result_data,
            error_message=attempt.error_message,
            error_type=attempt.error_type,
        )

    async def mark_completed(self, attempt_id: UUID, completed_at: datetime) -> None:
        result = await self._session.execute(
            update(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .where(TaskAttemptRecord.status == "result_recorded")
            .values(
                status="completed",
                completed_at=completed_at,
                completion_published_at=completed_at,
                claim_expires_at=None,
            )
            .returning(TaskAttemptRecord.attempt_id)
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"Attempt '{attempt_id}' is not available to mark completed.")

    async def renew_claim(
        self,
        attempt_id: UUID,
        worker_id: str,
        claim_expires_at: datetime,
    ) -> bool:
        result = await self._session.execute(
            update(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .where(TaskAttemptRecord.status == "claimed")
            .where(TaskAttemptRecord.claimed_by == worker_id)
            .values(claim_expires_at=claim_expires_at)
            .returning(TaskAttemptRecord.attempt_id)
        )
        return result.scalar_one_or_none() is not None
