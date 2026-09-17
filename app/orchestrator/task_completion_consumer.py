"""Redis consumer for worker-reported task completion events."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from app.domain.repositories.unit_of_work import UnitOfWork
from app.messaging.redis.barriers import participate_in_barrier
from app.messaging.redis.client import get_async_redis_client
from app.messaging.redis.streams import (
    ORCHESTRATOR_COMPLETIONS_GROUP,
    WORKFLOW_TASK_COMPLETIONS_STREAM,
    ack,
    consume,
)
from app.messaging.task_completion import TaskCompletionEvent
from app.services.task_completion_service import (
    RetryPolicy,
    TaskCompletionDecision,
    TaskCompletionService,
)
from app.services.workflow_dispatch_service import WorkflowDispatchService

logger = logging.getLogger(__name__)


class TaskCompletionProcessor(Protocol):
    """Contract for persisting one parsed completion event."""

    async def process(self, event: TaskCompletionEvent, unit_of_work: UnitOfWork) -> object:
        """Persist a completion event."""


class ReadyNodeDispatcher(Protocol):
    """Contract for dispatching nodes promoted by task completion."""

    async def dispatch_ready(
        self,
        execution_id: UUID,
        ready_node_ids: tuple[str, ...],
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> object:
        """Dispatch the supplied ready workflow nodes."""


class TaskCompletionConsumer:
    """Consume and persist worker completion events from Redis Streams."""

    def __init__(
        self,
        consumer_name: str,
        unit_of_work_factory: Callable[[], UnitOfWork],
        completion_service: TaskCompletionProcessor | None = None,
        dispatch_service: ReadyNodeDispatcher | None = None,
    ) -> None:
        self._consumer_name = consumer_name
        self._unit_of_work_factory = unit_of_work_factory
        self._completion_service = completion_service or TaskCompletionService(
            retry_policy=RetryPolicy.from_environment()
        )
        self._dispatch_service = dispatch_service or WorkflowDispatchService()

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
                logger.info(
                    "Orchestrator received task completion",
                    extra={"message_id": message_id, "stream": stream},
                )
                event = TaskCompletionEvent.from_stream_fields(fields)
                await _wait_for_integration_barrier(event)
                decision = await self._completion_service.process(
                    event, self._unit_of_work_factory()
                )
                logger.info(
                    "Orchestrator persisted task completion",
                    extra={
                        "message_id": message_id,
                        "execution_id": str(event.execution_id),
                        "node_id": event.node_id,
                    },
                )
                if isinstance(decision, TaskCompletionDecision):
                    await self._dispatch_service.dispatch_ready(
                        event.execution_id,
                        decision.ready_node_ids,
                        self._unit_of_work_factory,
                    )
                    logger.info(
                        "Orchestrator dispatched ready nodes",
                        extra={
                            "execution_id": str(event.execution_id),
                            "ready_node_ids": decision.ready_node_ids,
                        },
                    )
                await ack(stream, ORCHESTRATOR_COMPLETIONS_GROUP, message_id)
                logger.info(
                    "Orchestrator acknowledged task completion",
                    extra={"message_id": message_id, "stream": stream},
                )
                processed += 1
        return processed


async def _wait_for_integration_barrier(event: TaskCompletionEvent) -> None:
    """Synchronize selected completion events only in integration tests."""

    if os.getenv("INTEGRATION_TEST") != "1":
        return
    prefix = os.getenv("INTEGRATION_COMPLETION_BARRIER_PREFIX")
    barrier_nodes = {
        node_id
        for node_id in os.getenv("INTEGRATION_COMPLETION_BARRIER_NODES", "").split(",")
        if node_id
    }
    if not prefix or event.node_id not in barrier_nodes:
        return

    timeout_seconds = float(os.getenv("INTEGRATION_BARRIER_TIMEOUT_SECONDS", "30"))
    if timeout_seconds <= 0:
        raise ValueError("INTEGRATION_BARRIER_TIMEOUT_SECONDS must be greater than zero.")
    await participate_in_barrier(
        get_async_redis_client(),
        f"{prefix}:{event.execution_id}",
        event.node_id,
        timeout_seconds=timeout_seconds,
    )
