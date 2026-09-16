"""Orchestrator entrypoint for workflow outbox events."""

from __future__ import annotations

from datetime import timedelta

from app.db.session import AsyncSessionFactory
from app.messaging.outbox_publisher import OutboxPublisher


async def publish_outbox_events() -> int:
    """Publish pending workflow events from the transactional outbox."""

    return await OutboxPublisher(AsyncSessionFactory).publish_pending()


async def cleanup_published_outbox(retention_seconds: float) -> int:
    """Remove successfully published outbox messages past their retention period."""

    return await OutboxPublisher(AsyncSessionFactory).cleanup_published(
        retention=timedelta(seconds=retention_seconds)
    )
