"""Application service for persisting worker-reported node completion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus
from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.services.node_task_dispatcher import create_task_id
from app.services.workflow_finalization_service import WorkflowFinalizationService
from app.services.workflow_readiness_service import WorkflowReadinessService


class TaskCompletionOutcome(StrEnum):
    """Result of processing a worker completion event."""

    PROCESSED = "processed"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class TaskCompletionDecision:
    """The persisted outcome of one completion event."""

    event_id: str
    execution_id: str
    node_id: str
    outcome: TaskCompletionOutcome
    ready_node_ids: tuple[str, ...] = ()


class TaskCompletionService:
    """Persist worker completion events without executing worker business logic."""

    async def process(
        self,
        event: TaskCompletionEvent,
        unit_of_work: UnitOfWork,
    ) -> TaskCompletionDecision:
        """Apply an idempotent RUNNING-to-terminal node state transition."""

        if event.task_id != create_task_id(event.execution_id, event.node_id):
            raise ValueError("Task completion event task_id does not match its execution and node.")

        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id(
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
                output_data=event.output_data,
                error_message=event.error_message,
                error_type=event.error_type,
                completed_at=datetime.now(UTC),
            )

        if not updated:
            if existing_node.status not in {
                NodeExecutionStatus.COMPLETED,
                NodeExecutionStatus.FAILED,
                NodeExecutionStatus.SKIPPED,
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

        ready_node_ids: tuple[str, ...] = ()
        if event.status is TaskCompletionStatus.COMPLETED:
            readiness = await WorkflowReadinessService().evaluate(event.execution_id, unit_of_work)
            ready_node_ids = readiness.ready_node_ids
        await WorkflowFinalizationService().evaluate(event.execution_id, unit_of_work)

        return TaskCompletionDecision(
            event_id=str(event.event_id),
            execution_id=str(event.execution_id),
            node_id=event.node_id,
            outcome=TaskCompletionOutcome.PROCESSED,
            ready_node_ids=ready_node_ids,
        )
