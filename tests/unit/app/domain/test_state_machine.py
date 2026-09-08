from uuid import uuid4

import pytest

from app.domain.errors.transitions import (
    InvalidNodeTransitionError,
    InvalidWorkflowTransitionError,
)
from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.state.state_machine import NODE_TRANSITIONS, WORKFLOW_TRANSITIONS
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.RUNNING),
        (WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.COMPLETED),
        (WorkflowExecutionStatus.RUNNING, WorkflowExecutionStatus.FAILED),
    ],
)
def test_workflow_valid_transitions(
    current_status: WorkflowExecutionStatus, target_status: WorkflowExecutionStatus
) -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=current_status)
    transitioned = execution.transition_to(target_status)

    assert transitioned.status is target_status
    assert execution.status is current_status


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.COMPLETED),
        (WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.FAILED),
        (WorkflowExecutionStatus.COMPLETED, WorkflowExecutionStatus.RUNNING),
        (WorkflowExecutionStatus.FAILED, WorkflowExecutionStatus.RUNNING),
    ],
)
def test_workflow_invalid_transitions(
    current_status: WorkflowExecutionStatus, target_status: WorkflowExecutionStatus
) -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=current_status)

    with pytest.raises(InvalidWorkflowTransitionError):
        execution.transition_to(target_status)


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (NodeExecutionStatus.PENDING, NodeExecutionStatus.READY),
        (NodeExecutionStatus.PENDING, NodeExecutionStatus.SKIPPED),
        (NodeExecutionStatus.READY, NodeExecutionStatus.RUNNING),
        (NodeExecutionStatus.READY, NodeExecutionStatus.SKIPPED),
        (NodeExecutionStatus.RUNNING, NodeExecutionStatus.COMPLETED),
        (NodeExecutionStatus.RUNNING, NodeExecutionStatus.FAILED),
    ],
)
def test_node_valid_transitions(
    current_status: NodeExecutionStatus, target_status: NodeExecutionStatus
) -> None:
    execution = NodeExecution(
        workflow_execution_id=uuid4(),
        node_id="node-1",
        status=current_status,
    )
    transitioned = execution.transition_to(target_status)

    assert transitioned.status is target_status
    assert execution.status is current_status


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (NodeExecutionStatus.PENDING, NodeExecutionStatus.RUNNING),
        (NodeExecutionStatus.READY, NodeExecutionStatus.COMPLETED),
        (NodeExecutionStatus.COMPLETED, NodeExecutionStatus.RUNNING),
        (NodeExecutionStatus.FAILED, NodeExecutionStatus.READY),
        (NodeExecutionStatus.SKIPPED, NodeExecutionStatus.READY),
    ],
)
def test_node_invalid_transitions(
    current_status: NodeExecutionStatus, target_status: NodeExecutionStatus
) -> None:
    execution = NodeExecution(
        workflow_execution_id=uuid4(),
        node_id="node-1",
        status=current_status,
    )

    with pytest.raises(InvalidNodeTransitionError):
        execution.transition_to(target_status)


def test_workflow_terminal_states_have_no_outgoing_transitions() -> None:
    assert WORKFLOW_TRANSITIONS[WorkflowExecutionStatus.COMPLETED] == set()
    assert WORKFLOW_TRANSITIONS[WorkflowExecutionStatus.FAILED] == set()


def test_node_terminal_states_have_no_outgoing_transitions() -> None:
    assert NODE_TRANSITIONS[NodeExecutionStatus.COMPLETED] == set()
    assert NODE_TRANSITIONS[NodeExecutionStatus.FAILED] == set()
    assert NODE_TRANSITIONS[NodeExecutionStatus.SKIPPED] == set()
