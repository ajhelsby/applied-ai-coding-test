"""Application service for deriving terminal workflow execution state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus


@dataclass(frozen=True, slots=True)
class WorkflowFinalizationDecision:
    """The workflow state after evaluating terminal conditions."""

    execution_id: UUID
    status: WorkflowExecutionStatus


class WorkflowFinalizationService:
    """Transition running workflows to a terminal state when their nodes require it."""

    async def evaluate(
        self,
        execution_id: UUID,
        unit_of_work: UnitOfWork,
    ) -> WorkflowFinalizationDecision:
        """Fail on any failed node, or complete when every defined node completed."""

        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id(execution_id)
            if execution is None:
                raise WorkflowExecutionNotFoundError(str(execution_id))

            node_executions = await transaction.node_executions.get_node_executions_for_execution(
                execution_id
            )
            if any(item.status is NodeExecutionStatus.FAILED for item in node_executions):
                await transaction.workflow_executions.update_status_if_current(
                    execution_id=execution_id,
                    expected_current_status=WorkflowExecutionStatus.RUNNING,
                    new_status=WorkflowExecutionStatus.FAILED,
                    completed_at=datetime.now(UTC),
                )
                return WorkflowFinalizationDecision(
                    execution_id=execution_id,
                    status=WorkflowExecutionStatus.FAILED,
                )

            workflow = await transaction.workflows.get_workflow_by_id(execution.workflow_id)
            if workflow is None:
                raise LookupError(f"Workflow '{execution.workflow_id}' was not found.")

            node_statuses_by_id = {item.node_id: item.status for item in node_executions}
            if all(
                node_statuses_by_id.get(node.id) is NodeExecutionStatus.COMPLETED
                for node in workflow.dag.nodes
            ):
                await transaction.workflow_executions.update_status_if_current(
                    execution_id=execution_id,
                    expected_current_status=WorkflowExecutionStatus.RUNNING,
                    new_status=WorkflowExecutionStatus.COMPLETED,
                    completed_at=datetime.now(UTC),
                )
                return WorkflowFinalizationDecision(
                    execution_id=execution_id,
                    status=WorkflowExecutionStatus.COMPLETED,
                )

        return WorkflowFinalizationDecision(execution_id=execution_id, status=execution.status)
