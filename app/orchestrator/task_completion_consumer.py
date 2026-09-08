"""Redis consumer for worker-reported task completion events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.domain.repositories.unit_of_work import UnitOfWork
from app.messaging.redis.streams import (
    ORCHESTRATOR_COMPLETIONS_GROUP,
    WORKFLOW_TASK_COMPLETIONS_STREAM,
    ack,
    consume,
)
from app.messaging.task_completion import TaskCompletionEvent
from app.services.task_completion_service import TaskCompletionService


class TaskCompletionProcessor(Protocol):
    """Contract for persisting one parsed completion event."""

    async def process(self, event: TaskCompletionEvent, unit_of_work: UnitOfWork) -> object:
        """Persist a completion event."""


class TaskCompletionConsumer:
    """Consume and persist worker completion events from Redis Streams."""

    def __init__(
        self,
        consumer_name: str,
        unit_of_work_factory: Callable[[], UnitOfWork],
        completion_service: TaskCompletionProcessor | None = None,
    ) -> None:
        self._consumer_name = consumer_name
        self._unit_of_work_factory = unit_of_work_factory
        self._completion_service = completion_service or TaskCompletionService()

    async def consume_once(self) -> int:
        """Process available messages and acknowledge only persisted events."""

        messages = await consume(
            group=ORCHESTRATOR_COMPLETIONS_GROUP,
            consumer=self._consumer_name,
            streams={WORKFLOW_TASK_COMPLETIONS_STREAM: ">"},
            count=100,
            block_ms=1000,
        )
        processed = 0
        for stream, stream_messages in messages:
            for message_id, fields in stream_messages:
                event = TaskCompletionEvent.from_stream_fields(fields)
                await self._completion_service.process(event, self._unit_of_work_factory())
                await ack(stream, ORCHESTRATOR_COMPLETIONS_GROUP, message_id)
                processed += 1
        return processed
