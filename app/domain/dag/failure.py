"""Pure evaluation of nodes blocked by failed workflow dependencies."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping

from app.domain.dag.graph import DAG
from app.domain.models.workflow import Workflow
from app.domain.state.states import NodeExecutionStatus

_SKIPPABLE_STATUSES = frozenset(
    {
        NodeExecutionStatus.PENDING,
        NodeExecutionStatus.READY,
    }
)
_BLOCKING_STATUSES = frozenset(
    {
        NodeExecutionStatus.FAILED,
        NodeExecutionStatus.SKIPPED,
    }
)


def evaluate_failed_dependency_node_ids(
    workflow: Workflow,
    node_statuses_by_id: Mapping[str, NodeExecutionStatus],
) -> tuple[str, ...]:
    """Return pending or ready nodes made impossible by failed dependencies."""

    dag = DAG.from_workflow(workflow)
    statuses = dict(node_statuses_by_id)
    blocked_node_ids: set[str] = set()
    queue = deque(
        node.id
        for node in workflow.dag.nodes
        if statuses.get(node.id, NodeExecutionStatus.PENDING) in _BLOCKING_STATUSES
    )

    while queue:
        blocked_node_id = queue.popleft()
        for dependant in dag.get_dependants(blocked_node_id):
            dependant_status = statuses.get(dependant.node_id, NodeExecutionStatus.PENDING)
            if dependant_status not in _SKIPPABLE_STATUSES:
                continue
            if dependant.node_id in blocked_node_ids:
                continue

            blocked_node_ids.add(dependant.node_id)
            statuses[dependant.node_id] = NodeExecutionStatus.SKIPPED
            queue.append(dependant.node_id)

    return tuple(node.id for node in workflow.dag.nodes if node.id in blocked_node_ids)
