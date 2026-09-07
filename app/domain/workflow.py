"""Workflow domain model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.node import WorkflowNode


class Workflow(BaseModel):
    """Immutable workflow definition used as orchestration input."""

    # Pydantic provides shared, strongly-typed and JSON-friendly contracts
    # across service boundaries with minimal custom serialization code.
    model_config = ConfigDict(frozen=True)

    workflow_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None
