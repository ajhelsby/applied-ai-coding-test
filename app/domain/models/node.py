"""Workflow node domain model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowNode(BaseModel):
    """Shared node definition used by API, orchestrator and workers."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        min_length=1,
        description="Unique identifier for this node within the workflow DAG.",
        examples=["fetch"],
    )
    handler: str = Field(
        min_length=1,
        description="Supported handler type used to execute this node.",
        examples=["call_external_service"],
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Identifiers of nodes that must complete before this node can run.",
        examples=[["input"]],
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Handler-specific configuration. For call_external_service, this includes "
            "a URL that may contain workflow templates."
        ),
        examples=[{"url": "https://example.test/{{ input.value }}"}],
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp at which the node definition was created.",
    )
    created_by: str | None = Field(
        default=None,
        description="Optional identifier for the node definition creator.",
    )


class NodeReference(BaseModel):
    """Reference to a node within a workflow definition."""

    model_config = ConfigDict(frozen=True)

    workflow_id: UUID
    node_id: str = Field(min_length=1)
