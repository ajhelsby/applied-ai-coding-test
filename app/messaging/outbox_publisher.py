"""Transactional outbox publisher for workflow trigger events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from json import dumps

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.outbox_event import OutboxEventRecord
from app.messaging.redis.streams import WORKFLOW_EVENTS_STREAM, publish


class OutboxPublisher:
    """Drain durable outbox rows and publish them to Redis streams."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def publish_pending(self) -> int:
        """Publish pending outbox events and mark them as published.

        A publisher crash after Redis accepts a message but before this database
        transaction commits can result in a duplicate delivery. Consumers must
        use ``event_id`` for idempotency.
        """

        async with self._session_factory() as session:
            result = await session.execute(
                select(OutboxEventRecord)
                .where(OutboxEventRecord.status == "pending")
                .order_by(OutboxEventRecord.created_at.asc())
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            rows = list(result.scalars().all())
            published = 0
            for row in rows:
                try:
                    await publish(
                        WORKFLOW_EVENTS_STREAM,
                        {
                            "event_id": str(row.event_id),
                            "event_type": row.event_type,
                            "aggregate_id": str(row.aggregate_id),
                            "payload": dumps(row.payload, separators=(",", ":"), sort_keys=True),
                        },
                    )
                except RedisError as error:
                    row.publish_attempts += 1
                    row.last_error = str(error)
                    await session.commit()
                    raise
                row.status = "published"
                row.published_at = datetime.now(UTC)
                row.publish_attempts += 1
                row.last_error = None
                published += 1
            await session.commit()
            return published
