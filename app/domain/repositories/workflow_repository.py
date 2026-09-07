"""Workflow repository contract."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.workflow import Workflow


class WorkflowRepository(Protocol):
    """Persistence operations for workflow definitions."""

    async def create_workflow(self, workflow: Workflow) -> Workflow:
        """Persist a workflow definition."""

    async def get_workflow_by_id(self, workflow_id: UUID) -> Workflow | None:
        """Retrieve a workflow definition by ID."""
