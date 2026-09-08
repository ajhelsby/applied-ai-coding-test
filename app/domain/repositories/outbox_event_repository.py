"""Transactional outbox repository contract."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class OutboxEventRepository(Protocol):
    """Persistence operations for transactional outbox events."""

    async def add_execution_triggered(self, execution_id: UUID) -> None:
        """Store an execution-triggered event for asynchronous publication."""
