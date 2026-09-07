"""Domain-level exceptions."""

from __future__ import annotations

from app.domain.states import NodeExecutionStatus, WorkflowExecutionStatus


class InvalidWorkflowTransitionError(ValueError):
    """Raised when a workflow state transition is not allowed."""

    def __init__(
        self,
        current_status: WorkflowExecutionStatus,
        target_status: WorkflowExecutionStatus,
    ) -> None:
        super().__init__(
            f"Invalid workflow transition: {current_status.value} -> {target_status.value}"
        )
        self.current_status = current_status
        self.target_status = target_status


class InvalidNodeTransitionError(ValueError):
    """Raised when a node state transition is not allowed."""

    def __init__(
        self,
        current_status: NodeExecutionStatus,
        target_status: NodeExecutionStatus,
    ) -> None:
        super().__init__(
            f"Invalid node transition: {current_status.value} -> {target_status.value}"
        )
        self.current_status = current_status
        self.target_status = target_status
