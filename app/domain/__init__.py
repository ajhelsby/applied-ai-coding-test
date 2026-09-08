"""Shared domain models and enums for workflow services."""

from app.domain.errors.transitions import (
    InvalidNodeTransitionError,
    InvalidWorkflowTransitionError,
)
from app.domain.errors.validation import (
    InvalidWorkflowDefinitionError,
    WorkflowValidationError,
)
from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.models.node import NodeReference, WorkflowNode
from app.domain.models.workflow import Workflow, WorkflowDag
from app.domain.repositories import (
    NodeExecutionRepository,
    UnitOfWork,
    WorkflowExecutionRepository,
    WorkflowRepository,
)
from app.domain.state.state_machine import (
    NODE_TRANSITIONS,
    WORKFLOW_TRANSITIONS,
    validate_node_transition,
    validate_workflow_transition,
)
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.domain.validation.validator import (
    DefaultWorkflowRuleProvider,
    WorkflowRuleProvider,
    WorkflowValidationRule,
    WorkflowValidator,
    collect_rules,
)

__all__ = [
    "NodeExecution",
    "NodeExecutionStatus",
    "NODE_TRANSITIONS",
    "NodeReference",
    "InvalidNodeTransitionError",
    "InvalidWorkflowTransitionError",
    "InvalidWorkflowDefinitionError",
    "NodeExecutionRepository",
    "Workflow",
    "WorkflowDag",
    "WorkflowExecution",
    "WorkflowExecutionRepository",
    "WorkflowExecutionStatus",
    "WorkflowRepository",
    "WorkflowValidationError",
    "WorkflowRuleProvider",
    "WorkflowValidationRule",
    "WorkflowValidator",
    "DefaultWorkflowRuleProvider",
    "collect_rules",
    "WORKFLOW_TRANSITIONS",
    "WorkflowNode",
    "UnitOfWork",
    "validate_node_transition",
    "validate_workflow_transition",
]
