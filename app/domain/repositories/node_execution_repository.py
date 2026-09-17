"""Node execution repository contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.models.execution import NodeExecution
from app.domain.models.json import JsonValue
from app.domain.state.states import NodeExecutionStatus


@dataclass(frozen=True, slots=True)
class OutputDataNotProvided:
    """Marker for updates that should preserve the existing output."""


OUTPUT_DATA_NOT_PROVIDED = OutputDataNotProvided()


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
        output_data: JsonValue | OutputDataNotProvided = OUTPUT_DATA_NOT_PROVIDED,
        error_message: str | None = None,
        error_type: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Update node status only if current status matches expected status."""

    async def claim_pending_nodes(
        self,
        execution_id: UUID,
        node_ids: Sequence[str],
    ) -> tuple[str, ...]:
        """Atomically promote pending nodes to running and return claimed node IDs."""

    async def fail_pending_nodes(
        self,
        execution_id: UUID,
        node_ids: Sequence[str],
        *,
        reason: str,
        completed_at: datetime,
    ) -> tuple[str, ...]:
        """Atomically fail pending nodes and return the nodes transitioned."""
