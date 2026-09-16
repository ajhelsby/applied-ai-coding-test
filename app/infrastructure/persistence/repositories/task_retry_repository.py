"""SQLAlchemy implementation of durable retry decisions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.task_retry_repository import (
    DueRetryTask,
    RetryDecision,
    RetryDecisionOutcome,
    TaskRetryRepository,
)
from app.infrastructure.persistence.models.task_retry import (
    LogicalTaskRecord,
    TaskAttemptRecord,
    TaskRetryDispatchRecord,
)


class SqlAlchemyTaskRetryRepository(TaskRetryRepository):
    """Retry repository backed by PostgreSQL row-level locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_success(
        self,
        task_id: str,
        attempt_id: UUID,
        completion_event_id: UUID,
        completed_at: datetime,
    ) -> bool:
        logical_task = await self._get_logical_task(task_id)
        if logical_task is None:
            return True
        attempt = await self._get_attempt(attempt_id)
        if attempt is None or attempt.task_id != task_id:
            raise ValueError(f"Attempt '{attempt_id}' does not belong to task '{task_id}'.")
        if attempt.completion_event_id == completion_event_id:
            return False
        if attempt.status in {"completed", "failed"}:
            return False
        await self._session.execute(
            update(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .values(
                status="completed",
                completion_event_id=completion_event_id,
                completed_at=completed_at,
                updated_at=completed_at,
            )
        )
        await self._session.execute(
            update(LogicalTaskRecord)
            .where(LogicalTaskRecord.task_id == task_id)
            .values(status="completed", updated_at=completed_at)
        )
        return True

    async def record_failure(
        self,
        task_id: str,
        attempt_id: UUID,
        failure_event_id: UUID,
        error_message: str,
        error_type: str,
        failed_at: datetime,
        max_attempts: int,
        retry_at: datetime,
    ) -> RetryDecision:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one.")
        logical_task = await self._get_logical_task(task_id)
        if logical_task is None:
            return RetryDecision(RetryDecisionOutcome.EXHAUSTED)
        duplicate = await self._session.execute(
            select(TaskAttemptRecord.attempt_id)
            .where(TaskAttemptRecord.failure_event_id == failure_event_id)
            .with_for_update()
        )
        if duplicate.scalar_one_or_none() is not None:
            return RetryDecision(RetryDecisionOutcome.DUPLICATE)

        attempt = await self._get_attempt(attempt_id)
        if attempt is None or attempt.task_id != task_id:
            raise ValueError(f"Attempt '{attempt_id}' does not belong to task '{task_id}'.")
        if attempt.status in {"completed", "failed"}:
            return RetryDecision(RetryDecisionOutcome.DUPLICATE)

        await self._session.execute(
            update(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .values(
                status="failed",
                failure_event_id=failure_event_id,
                error_message=error_message,
                error_type=error_type,
                failed_at=failed_at,
                updated_at=failed_at,
            )
        )
        if attempt.attempt_number >= max_attempts:
            await self._session.execute(
                update(LogicalTaskRecord)
                .where(LogicalTaskRecord.task_id == task_id)
                .values(
                    status="failed",
                    final_error_message=error_message,
                    final_error_type=error_type,
                    updated_at=failed_at,
                )
            )
            return RetryDecision(RetryDecisionOutcome.EXHAUSTED)

        next_attempt_id = uuid4()
        next_attempt_number = attempt.attempt_number + 1
        await self._session.execute(
            insert(TaskAttemptRecord).values(
                attempt_id=next_attempt_id,
                task_id=task_id,
                attempt_number=next_attempt_number,
                status="scheduled",
                scheduled_at=retry_at,
                created_at=failed_at,
                updated_at=failed_at,
            )
        )
        await self._session.execute(
            insert(TaskRetryDispatchRecord).values(
                attempt_id=next_attempt_id,
                available_at=retry_at,
                status="pending",
                created_at=failed_at,
            )
        )
        await self._session.execute(
            update(LogicalTaskRecord)
            .where(LogicalTaskRecord.task_id == task_id)
            .values(status="retry_scheduled", updated_at=failed_at)
        )
        return RetryDecision(
            RetryDecisionOutcome.RETRY_SCHEDULED,
            next_attempt_id=next_attempt_id,
            next_attempt_number=next_attempt_number,
        )

    async def register_initial_task(
        self,
        task_id: str,
        execution_id: UUID,
        node_id: str,
        handler: str,
        handler_config: dict[str, object],
        resolved_input: dict[str, object],
        attempt_id: UUID,
        started_at: datetime,
    ) -> UUID:
        await self._session.execute(
            insert(LogicalTaskRecord)
            .values(
                task_id=task_id,
                execution_id=execution_id,
                node_id=node_id,
                handler=handler,
                handler_config=handler_config,
                resolved_input=resolved_input,
                status="running",
                created_at=started_at,
                updated_at=started_at,
            )
            .on_conflict_do_nothing(index_elements=[LogicalTaskRecord.task_id])
        )
        existing_attempt = await self._session.execute(
            select(TaskAttemptRecord.attempt_id)
            .where(TaskAttemptRecord.task_id == task_id)
            .where(TaskAttemptRecord.attempt_number == 1)
        )
        existing_attempt_id = existing_attempt.scalar_one_or_none()
        if existing_attempt_id is not None:
            return existing_attempt_id
        await self._session.execute(
            insert(TaskAttemptRecord).values(
                attempt_id=attempt_id,
                task_id=task_id,
                attempt_number=1,
                status="running",
                started_at=started_at,
                created_at=started_at,
                updated_at=started_at,
            )
        )
        return attempt_id

    async def get_due_retries(self, available_at: datetime) -> list[DueRetryTask]:
        result = await self._session.execute(
            select(
                LogicalTaskRecord,
                TaskAttemptRecord,
            )
            .join(
                TaskRetryDispatchRecord,
                TaskRetryDispatchRecord.attempt_id == TaskAttemptRecord.attempt_id,
            )
            .where(TaskRetryDispatchRecord.status == "pending")
            .where(TaskRetryDispatchRecord.available_at <= available_at)
            .where(TaskAttemptRecord.status == "scheduled")
        )
        return [
            DueRetryTask(
                task_id=logical_task.task_id,
                attempt_id=attempt.attempt_id,
                attempt_number=attempt.attempt_number,
                execution_id=logical_task.execution_id,
                node_id=logical_task.node_id,
                handler=logical_task.handler,
                handler_config=logical_task.handler_config,
                resolved_input=logical_task.resolved_input,
            )
            for logical_task, attempt in result.all()
        ]

    async def mark_retry_published(self, attempt_id: UUID, published_at: datetime) -> bool:
        result = await self._session.execute(
            update(TaskRetryDispatchRecord)
            .where(TaskRetryDispatchRecord.attempt_id == attempt_id)
            .where(TaskRetryDispatchRecord.status == "pending")
            .values(
                status="published",
                published_at=published_at,
            )
            .returning(TaskRetryDispatchRecord.attempt_id)
        )
        if result.scalar_one_or_none() is None:
            return False
        await self._session.execute(
            update(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .where(TaskAttemptRecord.status == "scheduled")
            .values(status="queued", updated_at=published_at)
        )
        return True

    async def _get_logical_task(self, task_id: str) -> LogicalTaskRecord | None:
        result = await self._session.execute(
            select(LogicalTaskRecord).where(LogicalTaskRecord.task_id == task_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def _get_attempt(self, attempt_id: UUID) -> TaskAttemptRecord | None:
        result = await self._session.execute(
            select(TaskAttemptRecord)
            .where(TaskAttemptRecord.attempt_id == attempt_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()
