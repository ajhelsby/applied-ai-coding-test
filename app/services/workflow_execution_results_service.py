"""Application service for retrieving final persisted workflow results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.models.execution import WorkflowExecution
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.services.workflow_execution_status_service import WorkflowExecutionStatusService


@dataclass(frozen=True, slots=True)
class WorkflowNodeResult:
    """Final output produced by an individual completed workflow node."""

    node_id: str
    status: NodeExecutionStatus
    output_data: dict[str, Any]
    error_message: str | None
    error_type: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkflowExecutionResults:
    """Result availability and final node outputs for a workflow execution."""

    execution: WorkflowExecution
    message: str | None
    results: list[WorkflowNodeResult] | None


class WorkflowExecutionResultsService:
    """Retrieve final workflow results without changing persisted state.

    Invariant: if any node execution fails, the workflow execution status is FAILED.
    Therefore, COMPLETED is treated as successful completion for final results.
    A defensive guard still checks for inconsistent persisted state.
    """

    async def get(
        self,
        execution_id: UUID,
        unit_of_work: UnitOfWork,
    ) -> WorkflowExecutionResults | None:
        """Retrieve persisted workflow results and apply result availability policy."""

        workflow_status = await WorkflowExecutionStatusService().get(execution_id, unit_of_work)
        if workflow_status is None:
            return None

        execution = workflow_status.execution
        if execution.status is WorkflowExecutionStatus.PENDING:
            return WorkflowExecutionResults(
                execution=execution,
                message="Workflow execution is pending. Results are not available yet.",
                results=None,
            )
        if execution.status is WorkflowExecutionStatus.RUNNING:
            return WorkflowExecutionResults(
                execution=execution,
                message="Workflow execution is running. Results are not available yet.",
                results=None,
            )
        if execution.status is WorkflowExecutionStatus.FAILED:
            return WorkflowExecutionResults(
                execution=execution,
                message="Workflow execution failed. Final results are not available.",
                results=None,
            )
        if any(
            node_execution.status is NodeExecutionStatus.FAILED
            for node_execution in workflow_status.node_executions
        ):
            return WorkflowExecutionResults(
                execution=execution,
                message=(
                    "Workflow execution state is inconsistent: completed execution contains "
                    "failed node executions. Final results are not available."
                ),
                results=None,
            )

        return WorkflowExecutionResults(
            execution=execution,
            message=None,
            results=[
                WorkflowNodeResult(
                    node_id=node_execution.node_id,
                    status=node_execution.status,
                    output_data=node_execution.output_data,
                    error_message=node_execution.error_message,
                    error_type=node_execution.error_type,
                    created_at=node_execution.created_at,
                    started_at=node_execution.started_at,
                    completed_at=node_execution.completed_at,
                )
                for node_execution in workflow_status.node_executions
                if node_execution.status is NodeExecutionStatus.COMPLETED
            ],
        )
