"""Dispatch nodes that have already been promoted to ready."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.services.node_task_dispatcher import (
    DispatchResult,
    NodeTaskDispatcher,
    RedisNodeTaskDispatcher,
    UnitOfWorkFactory,
)


@dataclass(frozen=True, slots=True)
class WorkflowDispatchDecision:
    """The task-dispatch results for a set of ready workflow nodes."""

    execution_id: UUID
    results: list[DispatchResult]


class WorkflowDispatchService:
    """Load ready nodes and dispatch them through the worker task transport."""

    def __init__(self, dispatcher: NodeTaskDispatcher | None = None) -> None:
        self._dispatcher = dispatcher or RedisNodeTaskDispatcher()

    async def dispatch_ready(
        self,
        execution_id: UUID,
        ready_node_ids: tuple[str, ...],
        unit_of_work_factory: UnitOfWorkFactory,
    ) -> WorkflowDispatchDecision:
        """Dispatch the specified ready nodes without re-evaluating dependencies."""

        if not ready_node_ids:
            return WorkflowDispatchDecision(execution_id=execution_id, results=[])

        unit_of_work = unit_of_work_factory()
        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id(execution_id)
            if execution is None:
                raise WorkflowExecutionNotFoundError(str(execution_id))

            workflow = await transaction.workflows.get_workflow_by_id(execution.workflow_id)
            if workflow is None:
                raise LookupError(f"Workflow '{execution.workflow_id}' was not found.")

            ready_node_id_set = frozenset(ready_node_ids)
            nodes = [node for node in workflow.dag.nodes if node.id in ready_node_id_set]

        results = await self._dispatcher.dispatch_many(execution, nodes, unit_of_work_factory)
        return WorkflowDispatchDecision(execution_id=execution_id, results=results)
