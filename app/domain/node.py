"""Workflow node domain model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowNode(BaseModel):
    """Shared node definition used by API, orchestrator and workers."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    handler: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None


class NodeReference(BaseModel):
    """Reference to a node within a workflow definition."""

    model_config = ConfigDict(frozen=True)

    workflow_id: UUID
    node_id: str = Field(min_length=1)
