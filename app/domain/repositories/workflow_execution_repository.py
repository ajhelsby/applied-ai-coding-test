"""Workflow execution repository contract."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.execution import WorkflowExecution
from app.domain.states import WorkflowExecutionStatus


class WorkflowExecutionRepository(Protocol):
    """Persistence operations for workflow executions."""

    async def create_execution(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Persist a workflow execution."""

    async def get_execution_by_id(self, execution_id: UUID) -> WorkflowExecution | None:
        """Retrieve a workflow execution by ID."""

    async def update_status_if_current(
        self,
        execution_id: UUID,
        expected_current_status: WorkflowExecutionStatus,
        new_status: WorkflowExecutionStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Update execution status only if current status matches expected status."""
