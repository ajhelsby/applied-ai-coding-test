"""Contracts for dispatching runnable workflow nodes as asynchronous tasks."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4, uuid5

from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.models.execution import WorkflowExecution
from app.domain.models.node import WorkflowNode
from app.domain.repositories.task_retry_repository import TaskRetryRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus
from app.messaging.redis.streams import WORKFLOW_TASKS_STREAM, publish
from app.messaging.task_messages import NodeTaskMessage
from app.services.templates.resolver import NodeInputResolver

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
        unit_of_work: UnitOfWork,
    ) -> DispatchResult:
        """Dispatch a single eligible node as a task message."""

    async def dispatch_many(
        self,
        execution: WorkflowExecution,
        nodes: list[WorkflowNode],
        unit_of_work_factory: UnitOfWorkFactory,
    ) -> list[DispatchResult]:
        """Dispatch multiple eligible nodes independently."""


class RedisNodeTaskDispatcher(NodeTaskDispatcher):
    """Claim runnable nodes and publish worker-agnostic tasks to Redis Streams."""

    def __init__(
        self,
        task_publisher: TaskPublisher = publish,
        input_resolver: NodeInputResolver | None = None,
    ) -> None:
        self._task_publisher = task_publisher
        self._input_resolver = input_resolver or NodeInputResolver()

    async def dispatch(
        self,
        execution: WorkflowExecution,
        node: WorkflowNode,
        unit_of_work: UnitOfWork,
    ) -> DispatchResult:
        """Resolve, claim, then publish a ready node task."""

        task_id = create_task_id(execution.execution_id, node.id)
        async with unit_of_work.transaction() as transaction:
            if (
                await transaction.workflow_executions.get_execution_by_id_for_update(
                    execution.execution_id
                )
                is None
            ):
                raise WorkflowExecutionNotFoundError(str(execution.execution_id))

            node_executions = await transaction.node_executions.get_node_executions_for_execution(
                execution.execution_id
            )
            dependency_statuses = {
                node_execution.node_id: node_execution.status for node_execution in node_executions
            }
            if any(
                dependency_statuses.get(dependency_id)
                in {
                    NodeExecutionStatus.FAILED,
                }
                for dependency_id in node.dependencies
            ):
                await transaction.node_executions.fail_pending_nodes(
                    execution.execution_id,
                    (node.id,),
                    reason="A required dependency failed.",
                    completed_at=datetime.now(UTC),
                )
                return DispatchResult(
                    execution_id=execution.execution_id,
                    node_id=node.id,
                    task_id=task_id,
                    outcome=DispatchOutcome.ALREADY_STARTED,
                    reason="A required dependency failed; node was marked failed.",
                )

            completed_dependency_outputs = {
                node_execution.node_id: node_execution.output_data
                for node_execution in node_executions
                if node_execution.workflow_execution_id == execution.execution_id
                and node_execution.node_id in node.dependencies
                and node_execution.status is NodeExecutionStatus.COMPLETED
            }
            resolved_input = self._input_resolver.resolve(
                node,
                execution.input_data,
                completed_dependency_outputs,
            )
            claimed = await transaction.node_executions.update_status_if_current(
                execution_id=execution.execution_id,
                node_id=node.id,
                expected_current_status=NodeExecutionStatus.PENDING,
                new_status=NodeExecutionStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
            attempt_id = uuid4()
            retry_repository = self._retry_repository(transaction)
            if claimed and retry_repository is not None:
                attempt_id = await retry_repository.register_initial_task(
                    task_id=task_id,
                    execution_id=execution.execution_id,
                    node_id=node.id,
                    handler=node.handler,
                    handler_config=node.config,
                    resolved_input=resolved_input,
                    attempt_id=attempt_id,
                    started_at=datetime.now(UTC),
                )
            if claimed:
                task_message = NodeTaskMessage(
                    task_id=task_id,
                    attempt_id=attempt_id,
                    attempt_number=1,
                    execution_id=execution.execution_id,
                    node_id=node.id,
                    handler=node.handler,
                    handler_config=node.config,
                    resolved_input=resolved_input,
                )
                await transaction.outbox_events.add_task(
                    message_id=UUID(task_id),
                    aggregate_id=execution.execution_id,
                    payload={
                        "task_id": task_message.task_id,
                        "attempt_id": str(task_message.attempt_id),
                        "attempt_number": task_message.attempt_number,
                        "execution_id": str(task_message.execution_id),
                        "node_id": task_message.node_id,
                        "handler": task_message.handler,
                        "handler_config": task_message.handler_config,
                        "resolved_input": task_message.resolved_input,
                    },
                )

        if not claimed:
            return DispatchResult(
                execution_id=execution.execution_id,
                node_id=node.id,
                task_id=task_id,
                outcome=DispatchOutcome.ALREADY_STARTED,
                reason="Node was already dispatched or is no longer eligible to dispatch.",
            )

        return DispatchResult(
            execution_id=execution.execution_id,
            node_id=node.id,
            task_id=task_id,
            outcome=DispatchOutcome.DISPATCHED,
        )

    async def publish_due_retries(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        now: datetime | None = None,
    ) -> int:
        """Publish due retry attempts and durably mark each publication."""

        available_at = now or datetime.now(UTC)
        unit_of_work = unit_of_work_factory()
        async with unit_of_work.transaction() as transaction:
            retry_repository = self._retry_repository(transaction)
            if retry_repository is None:
                return 0
            due_retries = await retry_repository.get_due_retries(available_at)

        published = 0
        for retry in due_retries:
            await self._task_publisher(
                WORKFLOW_TASKS_STREAM,
                NodeTaskMessage(
                    task_id=retry.task_id,
                    attempt_id=retry.attempt_id,
                    attempt_number=retry.attempt_number,
                    execution_id=retry.execution_id,
                    node_id=retry.node_id,
                    handler=retry.handler,
                    handler_config=retry.handler_config,
                    resolved_input=retry.resolved_input,
                ).to_stream_fields(),
            )
            async with unit_of_work_factory().transaction() as transaction:
                retry_repository = self._retry_repository(transaction)
                if retry_repository is not None and await retry_repository.mark_retry_published(
                    retry.attempt_id, available_at
                ):
                    published += 1
        return published

    @staticmethod
    def _retry_repository(transaction: UnitOfWork) -> TaskRetryRepository | None:
        if not hasattr(transaction, "task_retries"):
            return None
        return transaction.task_retries

    async def dispatch_many(
        self,
        execution: WorkflowExecution,
        nodes: list[WorkflowNode],
        unit_of_work_factory: UnitOfWorkFactory,
    ) -> list[DispatchResult]:
        """Dispatch all eligible nodes concurrently with independent transactions."""

        results = await asyncio.gather(
            *(
                self.dispatch(
                    execution=execution,
                    node=node,
                    unit_of_work=unit_of_work_factory(),
                )
                for node in nodes
            )
        )
        return list(results)
