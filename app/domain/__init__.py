"""Shared domain models and enums for workflow services."""

from app.domain.exceptions import InvalidNodeTransitionError, InvalidWorkflowTransitionError
from app.domain.execution import NodeExecution, WorkflowExecution
from app.domain.node import NodeReference, WorkflowNode
from app.domain.repositories import (
    NodeExecutionRepository,
    UnitOfWork,
    WorkflowExecutionRepository,
    WorkflowRepository,
)
from app.domain.state_machine import (
    NODE_TRANSITIONS,
    WORKFLOW_TRANSITIONS,
    validate_node_transition,
    validate_workflow_transition,
)
from app.domain.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.domain.workflow import Workflow

__all__ = [
    "NodeExecution",
    "NodeExecutionStatus",
    "NODE_TRANSITIONS",
    "NodeReference",
    "InvalidNodeTransitionError",
    "InvalidWorkflowTransitionError",
    "NodeExecutionRepository",
    "Workflow",
    "WorkflowExecution",
    "WorkflowExecutionRepository",
    "WorkflowExecutionStatus",
    "WorkflowRepository",
    "WORKFLOW_TRANSITIONS",
    "WorkflowNode",
    "UnitOfWork",
    "validate_node_transition",
    "validate_workflow_transition",
]
