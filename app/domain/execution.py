"""Workflow and node execution domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.states import NodeExecutionStatus, WorkflowExecutionStatus


class WorkflowExecution(BaseModel):
    """A single run of a workflow definition."""

    model_config = ConfigDict(frozen=True)

    execution_id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING
    input_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class NodeExecution(BaseModel):
    """Execution record for an individual workflow node."""

    model_config = ConfigDict(frozen=True)

    workflow_execution_id: UUID
    node_id: str = Field(min_length=1)
    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    output_data: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    error_type: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
