"""Domain state enums shared across workflow services."""

from enum import StrEnum


class WorkflowExecutionStatus(StrEnum):
    """Lifecycle states for a workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class NodeExecutionStatus(StrEnum):
    """Lifecycle states for a node execution."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
