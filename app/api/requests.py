"""API request schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.node import WorkflowNode


class WorkflowDagRequest(BaseModel):
    """Workflow DAG payload used in submit requests."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[WorkflowNode] = Field(
        default_factory=list,
        description="Nodes that form the directed acyclic workflow graph.",
        examples=[
            [
                {
                    "id": "fetch",
                    "handler": "call_external_service",
                    "dependencies": ["input"],
                    "config": {"url": "https://example.test/{{ input.value }}"},
                }
            ]
        ],
    )


class WorkflowSubmissionRequest(BaseModel):
    """Workflow submission request payload."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="Human-readable name for the workflow definition.",
        examples=["document-enrichment"],
    )
    dag: WorkflowDagRequest = Field(
        default_factory=WorkflowDagRequest,
        description="Directed acyclic graph defining the workflow nodes and dependencies.",
    )
    created_by: str | None = Field(
        default=None,
        description="Optional identifier for the client or user submitting the workflow.",
        examples=["integration-test-client"],
    )


class WorkflowTriggerRequest(BaseModel):
    """Workflow trigger request payload."""

    model_config = ConfigDict(extra="forbid")

    input: dict[str, object] = Field(
        default_factory=dict,
        description=(
            "JSON-compatible input made available to workflow nodes. "
            "Values can be referenced by supported templates."
        ),
        examples=[{"value": "example-document", "options": {"draft": True}}],
    )
