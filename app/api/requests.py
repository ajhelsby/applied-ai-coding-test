"""API request schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.node import WorkflowNode


class WorkflowDagRequest(BaseModel):
    """Workflow DAG payload used in submit requests."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[WorkflowNode] = Field(default_factory=list)


class WorkflowSubmissionRequest(BaseModel):
    """Workflow submission request payload."""

    model_config = ConfigDict(extra="forbid")

    name: str
    dag: WorkflowDagRequest = Field(default_factory=WorkflowDagRequest)
    created_by: str | None = None


class WorkflowTriggerRequest(BaseModel):
    """Workflow trigger request payload."""

    model_config = ConfigDict(extra="forbid")

    input: dict[str, object] = Field(default_factory=dict)
