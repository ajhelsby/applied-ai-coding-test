"""Contracts for dispatching runnable workflow nodes as asynchronous tasks."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5

from redis.exceptions import RedisError

from app.domain.models.execution import WorkflowExecution
from app.domain.models.node import WorkflowNode
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus
from app.messaging.redis.streams import WORKFLOW_TASKS_STREAM, publish
from app.messaging.task_messages import NodeTaskMessage

TASK_ID_NAMESPACE = UUID("1f3cd7dd-05c9-48e9-9ad3-95520ee7ae8d")
TaskPublisher = Callable[[str, dict[str, str]], Awaitable[str]]
UnitOfWorkFactory = Callable[[], UnitOfWork]


def create_task_id(execution_id: UUID, node_id: str) -> str:
    """Create a stable task identifier for one node within one execution."""

    return str(uuid5(TASK_ID_NAMESPACE, f"{execution_id}:{node_id}"))


class DispatchOutcome(StrEnum):
    """Result of attempting to dispatch a runnable node."""

    DISPATCHED = "dispatched"
    ALREADY_STARTED = "already_started"
    FAILED_TO_PUBLISH = "failed_to_publish"


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Per-node dispatch attempt result."""

    execution_id: UUID
    node_id: str
    task_id: str | None
    outcome: DispatchOutcome
    reason: str | None = None


class NodeTaskDispatcher(Protocol):
    """Dispatch runnable workflow nodes to the asynchronous task stream."""

    async def dispatch(
        self,
        execution: WorkflowExecution,
        node: WorkflowNode,
        resolved_input: dict[str, object],
        unit_of_work: UnitOfWork,
    ) -> DispatchResult:
        """Dispatch a single eligible node as a task message."""

    async def dispatch_many(
        self,
        execution: WorkflowExecution,
        nodes_with_resolved_input: list[tuple[WorkflowNode, dict[str, object]]],
        unit_of_work_factory: UnitOfWorkFactory,
    ) -> list[DispatchResult]:
        """Dispatch multiple eligible nodes independently."""


class RedisNodeTaskDispatcher(NodeTaskDispatcher):
    """Claim runnable nodes and publish worker-agnostic tasks to Redis Streams."""

    def __init__(self, task_publisher: TaskPublisher = publish) -> None:
        self._task_publisher = task_publisher

    async def dispatch(
        self,
        execution: WorkflowExecution,
        node: WorkflowNode,
        resolved_input: dict[str, object],
        unit_of_work: UnitOfWork,
    ) -> DispatchResult:
        """Claim a ready node, then publish its task message."""

        task_id = create_task_id(execution.execution_id, node.id)
        async with unit_of_work.transaction() as transaction:
            claimed = await transaction.node_executions.update_status_if_current(
                execution_id=execution.execution_id,
                node_id=node.id,
                expected_current_status=NodeExecutionStatus.READY,
                new_status=NodeExecutionStatus.RUNNING,
                started_at=datetime.now(UTC),
            )

        if not claimed:
            return DispatchResult(
                execution_id=execution.execution_id,
                node_id=node.id,
                task_id=task_id,
                outcome=DispatchOutcome.ALREADY_STARTED,
                reason="Node was already dispatched or is no longer eligible to dispatch.",
            )

        try:
            await self._task_publisher(
                WORKFLOW_TASKS_STREAM,
                NodeTaskMessage(
                    task_id=task_id,
                    execution_id=execution.execution_id,
                    node_id=node.id,
                    handler=node.handler,
                    handler_config=node.config,
                    resolved_input=resolved_input,
                ).to_stream_fields(),
            )
        except RedisError as error:
            async with unit_of_work.transaction() as transaction:
                await transaction.node_executions.update_status_if_current(
                    execution_id=execution.execution_id,
                    node_id=node.id,
                    expected_current_status=NodeExecutionStatus.RUNNING,
                    new_status=NodeExecutionStatus.READY,
                    error_message=str(error),
                    error_type=type(error).__name__,
                )
            return DispatchResult(
                execution_id=execution.execution_id,
                node_id=node.id,
                task_id=task_id,
                outcome=DispatchOutcome.FAILED_TO_PUBLISH,
                reason=str(error),
            )

        return DispatchResult(
            execution_id=execution.execution_id,
            node_id=node.id,
            task_id=task_id,
            outcome=DispatchOutcome.DISPATCHED,
        )

    async def dispatch_many(
        self,
        execution: WorkflowExecution,
        nodes_with_resolved_input: list[tuple[WorkflowNode, dict[str, object]]],
        unit_of_work_factory: UnitOfWorkFactory,
    ) -> list[DispatchResult]:
        """Dispatch all eligible nodes concurrently with independent transactions."""

        results = await asyncio.gather(
            *(
                self.dispatch(
                    execution=execution,
                    node=node,
                    resolved_input=resolved_input,
                    unit_of_work=unit_of_work_factory(),
                )
                for node, resolved_input in nodes_with_resolved_input
            )
        )
        return list(results)
