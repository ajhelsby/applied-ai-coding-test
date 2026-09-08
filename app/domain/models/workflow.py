"""Workflow domain model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.node import WorkflowNode


class WorkflowDag(BaseModel):
    """Directed acyclic graph definition belonging to a workflow."""

    model_config = ConfigDict(frozen=True)

    nodes: list[WorkflowNode] = Field(default_factory=list)


class Workflow(BaseModel):
    """Immutable workflow definition used as orchestration input."""

    # Pydantic provides shared, strongly-typed and JSON-friendly contracts
    # across service boundaries with minimal custom serialization code.
    model_config = ConfigDict(frozen=True)

    workflow_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    dag: WorkflowDag = Field(default_factory=WorkflowDag)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None
