"""SQLAlchemy implementation of task-processing persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.json import JsonValue
from app.domain.repositories.task_processing_repository import (
    TaskClaimOutcome,
    TaskProcessingRepository,
    TaskProcessingResult,
)
from app.infrastructure.persistence.models.task_processing import TaskProcessingRecord


class SqlAlchemyTaskProcessingRepository(TaskProcessingRepository):
    """Task-processing repository backed by SQLAlchemy/PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_task(
        self,
        task_id: str,
        execution_id: UUID,
        node_id: str,
        worker_id: str,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> TaskClaimOutcome:
        inserted = await self._session.execute(
            insert(TaskProcessingRecord)
            .values(
                task_id=task_id,
                execution_id=execution_id,
                node_id=node_id,
                status="claimed",
                claimed_by=worker_id,
                claimed_at=claimed_at,
                claim_expires_at=claim_expires_at,
            )
            .on_conflict_do_nothing(index_elements=[TaskProcessingRecord.task_id])
            .returning(TaskProcessingRecord.task_id)
        )
        if inserted.scalar_one_or_none() is not None:
            return TaskClaimOutcome.CLAIMED

        existing = await self._session.execute(
            select(TaskProcessingRecord).where(TaskProcessingRecord.task_id == task_id)
        )
        existing_task = existing.scalar_one()
        if existing_task.execution_id != execution_id or existing_task.node_id != node_id:
            raise ValueError(
                f"Task '{task_id}' does not match its existing execution and node identity."
            )
        if existing_task.status == "completed":
            return TaskClaimOutcome.ALREADY_COMPLETED
        if existing_task.status == "result_recorded":
            return TaskClaimOutcome.RESULT_RECORDED

        reclaimed = await self._session.execute(
            update(TaskProcessingRecord)
            .where(TaskProcessingRecord.task_id == task_id)
            .where(TaskProcessingRecord.status != "completed")
            .where(
                and_(
                    TaskProcessingRecord.status == "claimed",
                    TaskProcessingRecord.claim_expires_at.is_not(None),
                    TaskProcessingRecord.claim_expires_at <= claimed_at,
                )
            )
            .values(
                execution_id=execution_id,
                node_id=node_id,
                claimed_by=worker_id,
                claimed_at=claimed_at,
                claim_expires_at=claim_expires_at,
            )
            .returning(TaskProcessingRecord.task_id)
        )
        if reclaimed.scalar_one_or_none() is not None:
            return TaskClaimOutcome.CLAIMED
        return TaskClaimOutcome.CURRENTLY_CLAIMED

    async def record_result(
        self,
        task_id: str,
        event_id: UUID,
        result_data: JsonValue,
        error_message: str | None,
        error_type: str | None,
    ) -> None:
        result = await self._session.execute(
            update(TaskProcessingRecord)
            .where(TaskProcessingRecord.task_id == task_id)
            .where(TaskProcessingRecord.status == "claimed")
            .values(
                status="result_recorded",
                result_data=result_data,
                error_message=error_message,
                error_type=error_type,
                completion_event_id=event_id,
            )
            .returning(TaskProcessingRecord.task_id)
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"Task '{task_id}' is not available to record a result.")

    async def get_result(self, task_id: str) -> TaskProcessingResult:
        result = await self._session.execute(
            select(TaskProcessingRecord).where(TaskProcessingRecord.task_id == task_id)
        )
        record = result.scalar_one()
        if record.completion_event_id is None:
            raise ValueError(f"Task '{task_id}' has no completion event to replay.")
        return TaskProcessingResult(
            event_id=record.completion_event_id,
            result_data=record.result_data,
            error_message=record.error_message,
            error_type=record.error_type,
        )

    async def mark_completed(self, task_id: str, completed_at: datetime) -> None:
        result = await self._session.execute(
            update(TaskProcessingRecord)
            .where(TaskProcessingRecord.task_id == task_id)
            .where(TaskProcessingRecord.status == "result_recorded")
            .values(
                status="completed",
                completed_at=completed_at,
                completion_published_at=completed_at,
                claim_expires_at=None,
            )
            .returning(TaskProcessingRecord.task_id)
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"Task '{task_id}' is not available to mark completed.")

    async def renew_claim(
        self,
        task_id: str,
        worker_id: str,
        claim_expires_at: datetime,
    ) -> bool:
        result = await self._session.execute(
            update(TaskProcessingRecord)
            .where(TaskProcessingRecord.task_id == task_id)
            .where(TaskProcessingRecord.status == "claimed")
            .where(TaskProcessingRecord.claimed_by == worker_id)
            .values(claim_expires_at=claim_expires_at)
            .returning(TaskProcessingRecord.task_id)
        )
        return result.scalar_one_or_none() is not None
