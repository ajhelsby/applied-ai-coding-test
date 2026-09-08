"""Validation-related domain errors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WorkflowValidationError:
    """Structured domain validation error for workflow definitions."""

    code: str
    message: str
    path: str
    node_id: str | None = None
    dependency_id: str | None = None
    meta: dict[str, str] = field(default_factory=dict)


class InvalidWorkflowDefinitionError(ValueError):
    """Raised when a workflow definition fails domain validation."""

    def __init__(self, errors: Sequence[WorkflowValidationError]) -> None:
        self.errors = tuple(errors)
        super().__init__(f"Workflow definition contains {len(self.errors)} validation error(s).")
