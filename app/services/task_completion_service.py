"""Application service for persisting worker-reported node completion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import pow
from uuid import uuid5

from app.domain.dag import evaluate_failed_dependency_node_ids
from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.repositories.task_retry_repository import (
    RetryDecisionOutcome,
    TaskRetryRepository,
)
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus
from app.messaging.redis.streams import WORKFLOW_EVENTS_STREAM
from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.services.node_task_dispatcher import create_task_id
from app.services.workflow_finalization_service import WorkflowFinalizationService
from app.services.workflow_readiness_service import WorkflowReadinessService


class TaskCompletionOutcome(StrEnum):
    """Result of processing a worker completion event."""

    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    RETRY_SCHEDULED = "retry_scheduled"


@dataclass(frozen=True, slots=True)
class TaskCompletionDecision:
    """The persisted outcome of one completion event."""

    event_id: str
    execution_id: str
    node_id: str
    outcome: TaskCompletionOutcome
    ready_node_ids: tuple[str, ...] = ()
    retry_attempt_id: str | None = None
    retry_attempt_number: int | None = None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry limits and delay calculation for failed task attempts."""

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one.")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must not be negative.")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least one.")
        if self.max_delay_seconds is not None and self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must not be negative.")

    @classmethod
    def from_environment(cls) -> RetryPolicy:
        """Build retry policy from validated process environment settings."""

        max_delay = os.getenv("WORKFLOW_TASK_RETRY_MAX_DELAY_SECONDS")
        return cls(
            max_attempts=int(os.getenv("WORKFLOW_TASK_MAX_ATTEMPTS", "3")),
            initial_delay_seconds=float(
                os.getenv("WORKFLOW_TASK_RETRY_INITIAL_DELAY_SECONDS", "1")
            ),
            backoff_multiplier=float(os.getenv("WORKFLOW_TASK_RETRY_BACKOFF_MULTIPLIER", "2")),
            max_delay_seconds=None if max_delay is None else float(max_delay),
        )

    def delay_for(self, attempt_number: int) -> float:
        if attempt_number < 1:
            raise ValueError("attempt_number must be at least one.")
        delay = self.initial_delay_seconds * pow(self.backoff_multiplier, attempt_number - 1)
        if self.max_delay_seconds is not None:
            delay = min(delay, self.max_delay_seconds)
        return delay


class TaskCompletionService:
    """Persist worker completion events without executing worker business logic."""

    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self._retry_policy = retry_policy or RetryPolicy()

    async def process(
        self,
        event: TaskCompletionEvent,
        unit_of_work: UnitOfWork,
    ) -> TaskCompletionDecision:
        """Apply an idempotent RUNNING-to-terminal node state transition."""

        if event.task_id != create_task_id(event.execution_id, event.node_id):
            raise ValueError("Task completion event task_id does not match its execution and node.")

        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id_for_update(
                event.execution_id
            )
            if execution is None:
                raise WorkflowExecutionNotFoundError(str(event.execution_id))

            node_executions = await transaction.node_executions.get_node_executions_for_execution(
                event.execution_id
            )
            existing_node = next(
                (
                    node_execution
                    for node_execution in node_executions
                    if node_execution.node_id == event.node_id
                ),
                None,
            )
            if existing_node is None:
                raise LookupError(
                    f"Node execution '{event.node_id}' was not found "
                    f"for execution '{event.execution_id}'."
                )

            retry_repository = self._retry_repository(transaction)
            if retry_repository is not None:
                if event.status is TaskCompletionStatus.COMPLETED:
                    recorded = await retry_repository.record_success(
                        task_id=event.task_id,
                        attempt_id=event.attempt_id,
                        completion_event_id=event.event_id,
                        completed_at=datetime.now(UTC),
                    )
                    if not recorded and existing_node.status is not NodeExecutionStatus.RUNNING:
                        return TaskCompletionDecision(
                            event_id=str(event.event_id),
                            execution_id=str(event.execution_id),
                            node_id=event.node_id,
                            outcome=TaskCompletionOutcome.DUPLICATE,
                        )
                else:
                    error_message = event.error_message
                    error_type = event.error_type
                    if error_message is None or error_type is None:
                        raise ValueError("Failed completion events require error information.")
                    retry_decision = await retry_repository.record_failure(
                        task_id=event.task_id,
                        attempt_id=event.attempt_id,
                        failure_event_id=event.event_id,
                        error_message=error_message,
                        error_type=error_type,
                        failed_at=datetime.now(UTC),
                        max_attempts=self._retry_policy.max_attempts,
                        retry_at=datetime.now(UTC)
                        + timedelta(seconds=self._retry_policy.delay_for(event.attempt_number)),
                    )
                    if retry_decision.outcome is RetryDecisionOutcome.DUPLICATE:
                        return TaskCompletionDecision(
                            event_id=str(event.event_id),
                            execution_id=str(event.execution_id),
                            node_id=event.node_id,
                            outcome=TaskCompletionOutcome.DUPLICATE,
                        )
                    if retry_decision.outcome is RetryDecisionOutcome.RETRY_SCHEDULED:
                        return TaskCompletionDecision(
                            event_id=str(event.event_id),
                            execution_id=str(event.execution_id),
                            node_id=event.node_id,
                            outcome=TaskCompletionOutcome.RETRY_SCHEDULED,
                            retry_attempt_id=str(retry_decision.next_attempt_id),
                            retry_attempt_number=retry_decision.next_attempt_number,
                        )

            completion_output = (
                event.output_data if event.status is TaskCompletionStatus.COMPLETED else None
            )
            completion_error_message = (
                event.error_message if event.status is TaskCompletionStatus.FAILED else None
            )
            completion_error_type = (
                event.error_type if event.status is TaskCompletionStatus.FAILED else None
            )
            target_status = (
                NodeExecutionStatus.COMPLETED
                if event.status is TaskCompletionStatus.COMPLETED
                else NodeExecutionStatus.FAILED
            )
            updated = await transaction.node_executions.update_status_if_current(
                execution_id=event.execution_id,
                node_id=event.node_id,
                expected_current_status=NodeExecutionStatus.RUNNING,
                new_status=target_status,
                output_data=completion_output,
                error_message=completion_error_message,
                error_type=completion_error_type,
                completed_at=datetime.now(UTC),
            )

            if not updated:
                if existing_node.status not in {
                    NodeExecutionStatus.COMPLETED,
                    NodeExecutionStatus.FAILED,
                }:
                    raise ValueError(
                        f"Node execution '{event.node_id}' cannot complete from "
                        f"status '{existing_node.status.value}'."
                    )
                return TaskCompletionDecision(
                    event_id=str(event.event_id),
                    execution_id=str(event.execution_id),
                    node_id=event.node_id,
                    outcome=TaskCompletionOutcome.DUPLICATE,
                )

            if event.status is TaskCompletionStatus.FAILED:
                workflow = await transaction.workflows.get_workflow_by_id(execution.workflow_id)
                if workflow is None:
                    raise LookupError(f"Workflow '{execution.workflow_id}' was not found.")

                statuses_by_id = {
                    node_execution.node_id: node_execution.status
                    for node_execution in node_executions
                }
                statuses_by_id[event.node_id] = NodeExecutionStatus.FAILED
                failed_dependency_node_ids = evaluate_failed_dependency_node_ids(
                    workflow,
                    statuses_by_id,
                )
                failed_dependency_node_ids = await transaction.node_executions.fail_pending_nodes(
                    event.execution_id,
                    failed_dependency_node_ids,
                    reason=f"Dependency '{event.node_id}' failed.",
                    completed_at=datetime.now(UTC),
                )
                for failed_node_id in failed_dependency_node_ids:
                    await transaction.outbox_events.add_message(
                        message_id=uuid5(
                            event.event_id,
                            f"node:{event.execution_id}:{failed_node_id}:failed",
                        ),
                        message_type="workflow.node.failed",
                        target_stream=WORKFLOW_EVENTS_STREAM,
                        aggregate_id=event.execution_id,
                        payload={
                            "execution_id": str(event.execution_id),
                            "node_id": failed_node_id,
                            "status": "failed",
                            "reason": f"Dependency '{event.node_id}' failed.",
                        },
                    )

            await transaction.outbox_events.add_message(
                message_id=event.event_id,
                message_type=f"workflow.node.{event.status.value}",
                target_stream=WORKFLOW_EVENTS_STREAM,
                aggregate_id=event.execution_id,
                payload={
                    "execution_id": str(event.execution_id),
                    "node_id": event.node_id,
                    "status": event.status.value,
                    "task_id": event.task_id,
                    "attempt_id": str(event.attempt_id),
                    "attempt_number": event.attempt_number,
                    "output_data": event.output_data,
                    "error_message": event.error_message,
                    "error_type": event.error_type,
                },
            )

            ready_node_ids: tuple[str, ...] = ()
            if event.status is TaskCompletionStatus.COMPLETED:
                readiness = await WorkflowReadinessService().evaluate_in_transaction(
                    event.execution_id,
                    transaction,
                    execution,
                )
                ready_node_ids = readiness.ready_node_ids
            await WorkflowFinalizationService().evaluate_in_transaction(
                event.execution_id,
                transaction,
                execution,
                correlation_id=event.event_id,
            )

            return TaskCompletionDecision(
                event_id=str(event.event_id),
                execution_id=str(event.execution_id),
                node_id=event.node_id,
                outcome=TaskCompletionOutcome.PROCESSED,
                ready_node_ids=ready_node_ids,
            )

    @staticmethod
    def _retry_repository(transaction: UnitOfWork) -> TaskRetryRepository | None:
        if not hasattr(transaction, "task_retries"):
            return None
        return transaction.task_retries
