"""Pure readiness evaluation for workflow node executions."""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.models.workflow import Workflow
from app.domain.state.states import NodeExecutionStatus

_NON_READY_STATUSES = frozenset(
    {
        NodeExecutionStatus.READY,
        NodeExecutionStatus.RUNNING,
        NodeExecutionStatus.COMPLETED,
        NodeExecutionStatus.FAILED,
        NodeExecutionStatus.SKIPPED,
    }
)


def evaluate_ready_node_ids(
    workflow: Workflow,
    node_statuses_by_id: Mapping[str, NodeExecutionStatus],
) -> tuple[str, ...]:
    """Return node IDs eligible to run, in workflow node order."""

    ready_node_ids: list[str] = []
    for node in workflow.dag.nodes:
        current_status = node_statuses_by_id.get(node.id, NodeExecutionStatus.PENDING)
        if current_status in _NON_READY_STATUSES:
            continue

        if all(
            node_statuses_by_id.get(dependency_id, NodeExecutionStatus.PENDING)
            is NodeExecutionStatus.COMPLETED
            for dependency_id in node.dependencies
        ):
            ready_node_ids.append(node.id)

    return tuple(ready_node_ids)
