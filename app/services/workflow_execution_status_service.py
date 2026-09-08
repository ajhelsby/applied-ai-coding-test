"""Application service for retrieving persisted workflow execution status."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.repositories.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class WorkflowExecutionStatus:
    """A workflow execution and the persisted state of its nodes."""

    execution: WorkflowExecution
    node_executions: list[NodeExecution]


class WorkflowExecutionStatusService:
    """Retrieve workflow execution status without changing persisted state."""

    async def get(
        self,
        execution_id: UUID,
        unit_of_work: UnitOfWork,
    ) -> WorkflowExecutionStatus | None:
        """Retrieve an execution and all of its node executions by execution ID."""

        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id(execution_id)
            if execution is None:
                return None
            node_executions = await transaction.node_executions.get_node_executions_for_execution(
                execution_id
            )

        return WorkflowExecutionStatus(
            execution=execution,
            node_executions=node_executions,
        )
