"""Transactional outbox publisher for workflow trigger events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from json import dumps

from redis.exceptions import RedisError
from sqlalchemy import delete, select
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
                        row.target_stream or WORKFLOW_EVENTS_STREAM,
                        _stream_fields(row),
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

    async def cleanup_published(
        self,
        retention: timedelta,
        batch_size: int = 100,
    ) -> int:
        """Delete only successfully published messages past the retention period."""
        if retention < timedelta(0):
            raise ValueError("retention must not be negative.")
        if batch_size < 1:
            raise ValueError("batch_size must be at least one.")

        cutoff = datetime.now(UTC) - retention
        async with self._session_factory() as session:
            result = await session.execute(
                select(OutboxEventRecord.event_id)
                .where(OutboxEventRecord.status == "published")
                .where(OutboxEventRecord.published_at <= cutoff)
                .order_by(OutboxEventRecord.published_at.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            message_ids = list(result.scalars().all())
            if not message_ids:
                await session.commit()
                return 0

            await session.execute(
                delete(OutboxEventRecord).where(OutboxEventRecord.event_id.in_(message_ids))
            )
            await session.commit()
            return len(message_ids)


def _stream_fields(row: OutboxEventRecord) -> dict[str, str]:
    """Serialize one generic outbox message for its target stream."""
    target_stream = row.target_stream or WORKFLOW_EVENTS_STREAM
    if target_stream == WORKFLOW_EVENTS_STREAM:
        fields = {
            "message_id": str(row.event_id),
            "event_id": str(row.event_id),
            "event_type": row.event_type,
            "payload": dumps(row.payload, separators=(",", ":"), sort_keys=True),
        }
        if row.aggregate_id is not None:
            fields["aggregate_id"] = str(row.aggregate_id)
        return fields

    return {
        "message_id": str(row.event_id),
        "message_type": row.event_type,
        **{key: _redis_field_value(value) for key, value in row.payload.items()},
    }


def _redis_field_value(value: object) -> str:
    """Encode JSON values as Redis stream field strings."""
    if isinstance(value, str):
        return value
    return dumps(value, separators=(",", ":"), sort_keys=True)
