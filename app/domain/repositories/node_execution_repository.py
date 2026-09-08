"""Node execution repository contract."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.models.execution import NodeExecution
from app.domain.state.states import NodeExecutionStatus


class NodeExecutionRepository(Protocol):
    """Persistence operations for node executions."""

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        """Retrieve node execution records for a workflow execution."""

    async def upsert_node_execution(self, node_execution: NodeExecution) -> NodeExecution:
        """Persist or update node execution state/output."""

    async def update_status_if_current(
        self,
        execution_id: UUID,
        node_id: str,
        expected_current_status: NodeExecutionStatus,
        new_status: NodeExecutionStatus,
        *,
        output_data: dict[str, object] | None = None,
        error_message: str | None = None,
        error_type: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Update node status only if current status matches expected status."""
