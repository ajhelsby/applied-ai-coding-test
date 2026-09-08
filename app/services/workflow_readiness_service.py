"""Application service for dependency-based node readiness evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.dag import evaluate_ready_node_ids
from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus


@dataclass(frozen=True, slots=True)
class WorkflowReadinessDecision:
    """Result of one readiness evaluation and promotion pass."""

    execution_id: UUID
    ready_node_ids: tuple[str, ...]


class WorkflowReadinessService:
    """Evaluate and promote runnable nodes to READY without dispatching."""

    async def evaluate(
        self,
        execution_id: UUID,
        unit_of_work: UnitOfWork,
    ) -> WorkflowReadinessDecision:
        """Evaluate readiness from persisted state and promote eligible PENDING nodes."""

        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id(execution_id)
            if execution is None:
                raise WorkflowExecutionNotFoundError(str(execution_id))

            workflow = await transaction.workflows.get_workflow_by_id(execution.workflow_id)
            if workflow is None:
                raise LookupError(f"Workflow '{execution.workflow_id}' was not found.")

            node_executions = await transaction.node_executions.get_node_executions_for_execution(
                execution_id
            )
            node_statuses_by_id = {item.node_id: item.status for item in node_executions}

            evaluated_ready_node_ids = evaluate_ready_node_ids(workflow, node_statuses_by_id)
            promoted_ready_node_ids: list[str] = []
            for node_id in evaluated_ready_node_ids:
                promoted = await transaction.node_executions.update_status_if_current(
                    execution_id=execution_id,
                    node_id=node_id,
                    expected_current_status=NodeExecutionStatus.PENDING,
                    new_status=NodeExecutionStatus.READY,
                )
                if promoted:
                    promoted_ready_node_ids.append(node_id)

        return WorkflowReadinessDecision(
            execution_id=execution_id,
            ready_node_ids=tuple(promoted_ready_node_ids),
        )
