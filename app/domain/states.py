"""Domain state enums shared across workflow services."""

from enum import StrEnum


class WorkflowExecutionStatus(StrEnum):
    """Lifecycle states for a workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeExecutionStatus(StrEnum):
    """Lifecycle states for a node execution."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
