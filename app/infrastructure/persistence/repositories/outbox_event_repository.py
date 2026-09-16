"""SQLAlchemy implementation of the transactional outbox repository."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.outbox_event_repository import OutboxEventRepository, OutboxPayload
from app.infrastructure.persistence.models.outbox_event import OutboxEventRecord


class SqlAlchemyOutboxEventRepository(OutboxEventRepository):
    """Persist messages for a separate publisher to deliver asynchronously."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_message(
        self,
        *,
        message_id: UUID,
        message_type: str,
        target_stream: str,
        payload: OutboxPayload,
        aggregate_id: UUID | None = None,
    ) -> None:
        """Add a message to the current database transaction."""
        self._session.add(
            OutboxEventRecord(
                event_id=message_id,
                event_type=message_type,
                target_stream=target_stream,
                aggregate_id=aggregate_id,
                payload=payload,
            )
        )

    async def add_execution_triggered(self, execution_id: UUID) -> None:
        """Store an execution-triggered event."""
        await self.add_message(
            message_id=uuid4(),
            message_type="workflow.execution.triggered",
            target_stream="workflow.events",
            aggregate_id=execution_id,
            payload={"execution_id": str(execution_id)},
        )

    async def add_task(
        self,
        *,
        message_id: UUID,
        payload: OutboxPayload,
        aggregate_id: UUID | None = None,
    ) -> None:
        """Store a workflow task for asynchronous publication."""
        await self.add_message(
            message_id=message_id,
            message_type="workflow.task",
            target_stream="workflow.tasks",
            aggregate_id=aggregate_id,
            payload=payload,
        )
