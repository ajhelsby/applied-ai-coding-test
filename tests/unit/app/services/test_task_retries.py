from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.models.workflow import Workflow
from app.domain.repositories.task_retry_repository import (
    RetryDecision,
    RetryDecisionOutcome,
)
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.services.node_task_dispatcher import create_task_id
from app.services.task_completion_service import (
    RetryPolicy,
    TaskCompletionDecision,
    TaskCompletionOutcome,
    TaskCompletionService,
)


class FakeRetryRepository:
    def __init__(self) -> None:
        self.attempts: dict[UUID, tuple[str, int]] = {}
        self.failure_events: set[UUID] = set()
        self.completed: set[UUID] = set()
        self.next_attempt_number = 2

    async def record_success(
        self,
        task_id: str,
        attempt_id: UUID,
        completion_event_id: UUID,
        completed_at: datetime,
    ) -> bool:
        del task_id, completion_event_id, completed_at
        if attempt_id in self.completed:
            return False
        self.completed.add(attempt_id)
        return True

    async def record_failure(
        self,
        task_id: str,
        attempt_id: UUID,
        failure_event_id: UUID,
        error_message: str,
        error_type: str,
        failed_at: datetime,
        max_attempts: int,
        retry_at: datetime,
    ) -> RetryDecision:
        del error_message, error_type, failed_at, retry_at
        if failure_event_id in self.failure_events:
            return RetryDecision(RetryDecisionOutcome.DUPLICATE)
        self.failure_events.add(failure_event_id)
        attempt_number = self.attempts.setdefault(attempt_id, (task_id, 1))[1]
        if attempt_number >= max_attempts:
            return RetryDecision(RetryDecisionOutcome.EXHAUSTED)
        next_attempt_id = uuid4()
        self.attempts[next_attempt_id] = (task_id, attempt_number + 1)
        decision = RetryDecision(
            RetryDecisionOutcome.RETRY_SCHEDULED,
            next_attempt_id=next_attempt_id,
            next_attempt_number=attempt_number + 1,
        )
        self.next_attempt_number = attempt_number + 1
        return decision


class FakeNodeExecutions:
    def __init__(self, execution_id: UUID, node_id: str) -> None:
        self.execution_id = execution_id
        self.node_id = node_id
        self.status = NodeExecutionStatus.RUNNING
        self.error: tuple[str | None, str | None] = (None, None)

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        return [
            NodeExecution(
                workflow_execution_id=execution_id,
                node_id=self.node_id,
                status=self.status,
            )
        ]

    async def update_status_if_current(
        self,
        execution_id: UUID,
        node_id: str,
        expected_current_status: NodeExecutionStatus,
        new_status: NodeExecutionStatus,
        *,
        error_message: str | None = None,
        error_type: str | None = None,
        **_kwargs: object,
    ) -> bool:
        del execution_id
        if node_id != self.node_id or self.status is not expected_current_status:
            return False
        self.status = new_status
        self.error = (error_message, error_type)
        return True

    async def claim_pending_nodes(
        self,
        execution_id: UUID,
        node_ids: Sequence[str],
    ) -> tuple[str, ...]:
        del execution_id, node_ids
        return ()

    async def fail_pending_nodes(
        self,
        execution_id: UUID,
        node_ids: Sequence[str],
        *,
        reason: str,
        completed_at: datetime,
    ) -> tuple[str, ...]:
        del execution_id, node_ids, reason, completed_at
        return ()


class FakeWorkflowExecutions:
    def __init__(self, execution: WorkflowExecution) -> None:
        self.execution = execution
        self.lock = asyncio.Lock()

    async def get_execution_by_id_for_update(self, execution_id: UUID) -> WorkflowExecution:
        await self.lock.acquire()
        if execution_id != self.execution.execution_id:
            raise LookupError("execution not found")
        return self.execution

    async def update_status_if_current(self, *args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False


class FakeWorkflows:
    async def get_workflow_by_id(self, workflow_id: UUID) -> Workflow:
        return Workflow(workflow_id=workflow_id, name="retry-test")


class FakeOutboxEvents:
    async def add_message(
        self,
        *,
        message_id: UUID,
        message_type: str,
        target_stream: str,
        payload: dict[str, object],
        aggregate_id: UUID | None = None,
    ) -> None:
        del message_id, message_type, target_stream, payload, aggregate_id


class FakeUnitOfWork:
    def __init__(self, execution: WorkflowExecution, node_id: str) -> None:
        self.workflow_executions = FakeWorkflowExecutions(execution)
        self.workflows = FakeWorkflows()
        self.node_executions = FakeNodeExecutions(execution.execution_id, node_id)
        self.task_retries = FakeRetryRepository()
        self.outbox_events = FakeOutboxEvents()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeUnitOfWork]:
        try:
            yield self
        finally:
            if self.workflow_executions.lock.locked():
                self.workflow_executions.lock.release()


def _event(
    execution_id: UUID,
    node_id: str,
    attempt_id: UUID,
    attempt_number: int,
    status: TaskCompletionStatus,
) -> TaskCompletionEvent:
    return TaskCompletionEvent(
        event_id=uuid4(),
        task_id=create_task_id(execution_id, node_id),
        attempt_id=attempt_id,
        attempt_number=attempt_number,
        execution_id=execution_id,
        node_id=node_id,
        status=status,
        output_data={"ok": True} if status is TaskCompletionStatus.COMPLETED else None,
        error_message="transient" if status is TaskCompletionStatus.FAILED else None,
        error_type="RuntimeError" if status is TaskCompletionStatus.FAILED else None,
    )


def test_retry_policy_applies_exponential_backoff_and_cap() -> None:
    policy = RetryPolicy(
        max_attempts=4,
        initial_delay_seconds=2,
        backoff_multiplier=3,
        max_delay_seconds=10,
    )

    assert policy.delay_for(1) == 2
    assert policy.delay_for(2) == 6
    assert policy.delay_for(3) == 10


def test_failed_attempt_is_retried_and_success_completes_node() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    uow = FakeUnitOfWork(execution, "node")
    first_attempt = uuid4()
    service = TaskCompletionService(RetryPolicy(max_attempts=2, initial_delay_seconds=0))

    first_decision = asyncio.run(
        service.process(
            _event(
                execution.execution_id,
                "node",
                first_attempt,
                1,
                TaskCompletionStatus.FAILED,
            ),
            uow,
        )
    )

    assert first_decision.outcome is TaskCompletionOutcome.RETRY_SCHEDULED
    assert first_decision.retry_attempt_id is not None
    assert first_decision.retry_attempt_number == 2
    assert uow.node_executions.status is NodeExecutionStatus.RUNNING

    second_attempt = UUID(first_decision.retry_attempt_id)
    success = asyncio.run(
        service.process(
            _event(
                execution.execution_id,
                "node",
                second_attempt,
                2,
                TaskCompletionStatus.COMPLETED,
            ),
            uow,
        )
    )

    assert success.outcome is TaskCompletionOutcome.PROCESSED
    assert uow.node_executions.status is NodeExecutionStatus.COMPLETED


def test_failure_at_maximum_attempt_marks_node_failed() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    uow = FakeUnitOfWork(execution, "node")
    service = TaskCompletionService(RetryPolicy(max_attempts=1))

    decision = asyncio.run(
        service.process(
            _event(execution.execution_id, "node", uuid4(), 1, TaskCompletionStatus.FAILED),
            uow,
        )
    )

    assert decision.outcome is TaskCompletionOutcome.PROCESSED
    assert uow.node_executions.status is NodeExecutionStatus.FAILED
    assert uow.node_executions.error == ("transient", "RuntimeError")


def test_duplicate_failure_event_does_not_schedule_another_attempt() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    uow = FakeUnitOfWork(execution, "node")
    service = TaskCompletionService(RetryPolicy(max_attempts=3))
    event = _event(execution.execution_id, "node", uuid4(), 1, TaskCompletionStatus.FAILED)

    first = asyncio.run(service.process(event, uow))
    duplicate = asyncio.run(service.process(event, uow))

    assert first.outcome is TaskCompletionOutcome.RETRY_SCHEDULED
    assert duplicate.outcome is TaskCompletionOutcome.DUPLICATE
    assert len(uow.task_retries.attempts) == 2


def test_concurrent_duplicate_failures_are_serialized() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    uow = FakeUnitOfWork(execution, "node")
    service = TaskCompletionService(RetryPolicy(max_attempts=3))
    event = _event(execution.execution_id, "node", uuid4(), 1, TaskCompletionStatus.FAILED)

    async def process_concurrently() -> list[TaskCompletionDecision]:
        return list(
            await asyncio.gather(
                service.process(event, uow),
                service.process(event, uow),
            )
        )

    decisions = asyncio.run(process_concurrently())

    assert sorted(decision.outcome for decision in decisions) == [
        TaskCompletionOutcome.DUPLICATE,
        TaskCompletionOutcome.RETRY_SCHEDULED,
    ]
    assert len(uow.task_retries.attempts) == 2
