"""Orchestrator entrypoint for workflow outbox events."""

from __future__ import annotations

from app.db.session import AsyncSessionFactory
from app.messaging.outbox_publisher import OutboxPublisher


async def publish_outbox_events() -> int:
    """Publish pending workflow events from the transactional outbox."""

    return await OutboxPublisher(AsyncSessionFactory).publish_pending()
