"""Transactional outbox repository contract."""

from __future__ import annotations

from typing import Protocol, TypeAlias
from uuid import UUID

OutboxPayload: TypeAlias = dict[str, object]  # noqa: UP040


class OutboxEventRepository(Protocol):
    """Transaction-scoped persistence operations for outbox messages."""

    async def add_message(
        self,
        *,
        message_id: UUID,
        message_type: str,
        target_stream: str,
        payload: OutboxPayload,
        aggregate_id: UUID | None = None,
    ) -> None:
        """Store one message for asynchronous publication."""

    async def add_execution_triggered(self, execution_id: UUID) -> None:
        """Store an execution-triggered event for asynchronous publication."""

    async def add_task(
        self,
        *,
        message_id: UUID,
        payload: OutboxPayload,
        aggregate_id: UUID | None = None,
    ) -> None:
        """Store a workflow task for asynchronous publication."""
