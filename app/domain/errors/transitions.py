"""Transition-related domain exceptions."""

from __future__ import annotations

from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus


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


class WorkflowExecutionNotFoundError(LookupError):
    """Raised when a workflow execution does not exist."""

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        super().__init__(f"Workflow execution '{execution_id}' was not found.")


class WorkflowExecutionNotTriggerableError(ValueError):
    """Raised when a workflow execution cannot be triggered from its current status."""

    def __init__(
        self,
        execution_id: str,
        status: WorkflowExecutionStatus,
    ) -> None:
        self.execution_id = execution_id
        self.status = status
        super().__init__(
            "Workflow execution cannot be triggered from status "
            f"'{status.value}' (execution_id={execution_id})."
        )
