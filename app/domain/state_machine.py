"""Declarative lifecycle transition maps for workflow and node executions."""

from __future__ import annotations

from app.domain.exceptions import InvalidNodeTransitionError, InvalidWorkflowTransitionError
from app.domain.states import NodeExecutionStatus, WorkflowExecutionStatus

WORKFLOW_TRANSITIONS: dict[WorkflowExecutionStatus, set[WorkflowExecutionStatus]] = {
    WorkflowExecutionStatus.PENDING: {
        WorkflowExecutionStatus.RUNNING,
    },
    WorkflowExecutionStatus.RUNNING: {
        WorkflowExecutionStatus.COMPLETED,
        WorkflowExecutionStatus.FAILED,
    },
    WorkflowExecutionStatus.COMPLETED: set(),
    WorkflowExecutionStatus.FAILED: set(),
}

NODE_TRANSITIONS: dict[NodeExecutionStatus, set[NodeExecutionStatus]] = {
    NodeExecutionStatus.PENDING: {
        NodeExecutionStatus.READY,
        NodeExecutionStatus.SKIPPED,
    },
    NodeExecutionStatus.READY: {
        NodeExecutionStatus.RUNNING,
        NodeExecutionStatus.SKIPPED,
    },
    NodeExecutionStatus.RUNNING: {
        NodeExecutionStatus.COMPLETED,
        NodeExecutionStatus.FAILED,
    },
    NodeExecutionStatus.COMPLETED: set(),
    NodeExecutionStatus.FAILED: set(),
    NodeExecutionStatus.SKIPPED: set(),
}


def validate_workflow_transition(
    current_status: WorkflowExecutionStatus,
    target_status: WorkflowExecutionStatus,
) -> None:
    """Validate a workflow status transition against the declarative map."""

    if target_status not in WORKFLOW_TRANSITIONS[current_status]:
        raise InvalidWorkflowTransitionError(current_status, target_status)


def validate_node_transition(
    current_status: NodeExecutionStatus,
    target_status: NodeExecutionStatus,
) -> None:
    """Validate a node status transition against the declarative map."""

    if target_status not in NODE_TRANSITIONS[current_status]:
        raise InvalidNodeTransitionError(current_status, target_status)
