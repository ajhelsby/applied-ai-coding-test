"""Application service for dependency-based node readiness evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.dag import evaluate_ready_node_ids
from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.models.execution import WorkflowExecution
from app.domain.repositories.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class WorkflowReadinessDecision:
    """Result of one readiness evaluation and promotion pass."""

    execution_id: UUID
    ready_node_ids: tuple[str, ...]


class WorkflowReadinessService:
    """Evaluate runnable pending nodes without dispatching."""

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

            decision = await self.evaluate_in_transaction(
                execution_id,
                transaction,
                execution,
            )
        return decision

    async def evaluate_in_transaction(
        self,
        execution_id: UUID,
        transaction: UnitOfWork,
        execution: WorkflowExecution | None = None,
    ) -> WorkflowReadinessDecision:
        """Evaluate readiness inside an existing transaction."""

        if execution is None:
            persisted_execution = await transaction.workflow_executions.get_execution_by_id(
                execution_id
            )
        else:
            persisted_execution = execution
        if persisted_execution is None:
            raise WorkflowExecutionNotFoundError(str(execution_id))

        workflow = await transaction.workflows.get_workflow_by_id(persisted_execution.workflow_id)
        if workflow is None:
            raise LookupError(f"Workflow '{persisted_execution.workflow_id}' was not found.")

        node_executions = await transaction.node_executions.get_node_executions_for_execution(
            execution_id
        )
        node_statuses_by_id = {item.node_id: item.status for item in node_executions}

        evaluated_ready_node_ids = evaluate_ready_node_ids(workflow, node_statuses_by_id)
        return WorkflowReadinessDecision(
            execution_id=execution_id,
            ready_node_ids=evaluated_ready_node_ids,
        )
