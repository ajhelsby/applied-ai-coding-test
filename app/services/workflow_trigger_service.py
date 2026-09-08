"""Application service for triggering existing workflow executions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain.errors.transitions import (
    WorkflowExecutionNotFoundError,
    WorkflowExecutionNotTriggerableError,
)
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import WorkflowExecutionStatus


@dataclass(frozen=True, slots=True)
class WorkflowTriggerDecision:
    """Decision returned after validating a workflow trigger request."""

    execution_id: UUID
    status: WorkflowExecutionStatus


class WorkflowTriggerService:
    """Validate whether a workflow execution can be triggered."""

    async def trigger(
        self,
        execution_id: UUID,
        input_data: dict[str, object] | None,
        unit_of_work: UnitOfWork,
    ) -> WorkflowTriggerDecision:
        """Atomically transition an execution and store its trigger event."""

        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id(execution_id)
            if execution is None:
                raise WorkflowExecutionNotFoundError(str(execution_id))
            if execution.status != WorkflowExecutionStatus.PENDING:
                raise WorkflowExecutionNotTriggerableError(str(execution_id), execution.status)

            transitioned = await transaction.workflow_executions.update_status_if_current(
                execution_id=execution_id,
                expected_current_status=WorkflowExecutionStatus.PENDING,
                new_status=WorkflowExecutionStatus.RUNNING,
                started_at=datetime.now(UTC),
                input_data=input_data,
            )
            if not transitioned:
                raise WorkflowExecutionNotTriggerableError(str(execution_id), execution.status)
            await transaction.outbox_events.add_execution_triggered(execution_id)

        return WorkflowTriggerDecision(
            execution_id=execution_id,
            status=WorkflowExecutionStatus.RUNNING,
        )
