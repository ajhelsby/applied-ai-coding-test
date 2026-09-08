"""Persistence-related application errors."""


class WorkflowPersistenceError(RuntimeError):
    """Raised when a workflow definition cannot be persisted."""
