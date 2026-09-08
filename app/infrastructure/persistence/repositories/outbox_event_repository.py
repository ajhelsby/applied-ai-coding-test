"""SQLAlchemy implementation of the transactional outbox repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.outbox_event_repository import OutboxEventRepository
from app.infrastructure.persistence.models.outbox_event import OutboxEventRecord


class SqlAlchemyOutboxEventRepository(OutboxEventRepository):
    """Persist events for a separate publisher to deliver asynchronously."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_execution_triggered(self, execution_id: UUID) -> None:
        self._session.add(
            OutboxEventRecord(
                event_type="workflow.execution.triggered",
                aggregate_id=execution_id,
                payload={"execution_id": str(execution_id)},
            )
        )
