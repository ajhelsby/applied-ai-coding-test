"""API response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.domain.models.json import JsonValue
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus


def _serialize_status(status: StrEnum) -> str:
    """Return persisted status values in their documented API form."""

    return status.value.upper()


class WorkflowSubmissionResponse(BaseModel):
    """Workflow submission success response payload."""

    execution_id: UUID = Field(
        description="Identifier of the pending execution created for the submitted workflow.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    name: str = Field(
        description="Name of the accepted workflow definition.",
        examples=["document-enrichment"],
    )
    created_at: datetime = Field(
        description="Timestamp at which the workflow execution was created.",
    )


class ValidationErrorItemResponse(BaseModel):
    """Structured validation failure item."""

    code: str = Field(
        description="Stable machine-readable validation error code.",
        examples=["unknown_dependency"],
    )
    message: str = Field(
        description="Human-readable explanation of the validation failure.",
        examples=["Node 'fetch' references unknown dependency 'missing'."],
    )
    path: str = Field(
        description="Location of the invalid value within the submitted request.",
        examples=["dag.nodes[1].dependencies[0]"],
    )
    node_id: str | None = Field(
        default=None,
        description="Node associated with the validation failure, when applicable.",
        examples=["fetch"],
    )
    dependency_id: str | None = Field(
        default=None,
        description="Referenced dependency associated with the failure, when applicable.",
        examples=["missing"],
    )
    meta: dict[str, str] = Field(
        default_factory=dict,
        description="Additional structured details about the validation failure.",
        examples=[{"cycle_path": "A->B->A"}],
    )


class ValidationErrorResponse(BaseModel):
    """Structured domain validation failure response payload."""

    error_code: str = Field(
        description="Stable machine-readable error category.",
        examples=["workflow_validation_failed"],
    )
    message: str = Field(
        description="Human-readable summary of the validation failure.",
        examples=["Workflow definition failed validation."],
    )
    errors: list[ValidationErrorItemResponse] = Field(
        description="Individual validation failures found in the workflow definition.",
    )


class PersistenceErrorResponse(BaseModel):
    """Workflow persistence failure response payload."""

    error_code: str = Field(
        description="Stable machine-readable persistence error category.",
        examples=["workflow_persistence_failed"],
    )
    message: str = Field(
        description="Human-readable explanation of the persistence failure.",
        examples=["Workflow could not be persisted. Please try again later."],
    )


class NodeExecutionStatusResponseItem(BaseModel):
    """Node execution status payload item."""

    node_id: str = Field(
        description="Identifier of the workflow node.",
        examples=["fetch"],
    )
    status: NodeExecutionStatus = Field(
        description="Current lifecycle state of this node execution.",
        examples=["COMPLETED"],
    )
    created_at: datetime = Field(description="Timestamp at which node execution was created.")
    started_at: datetime | None = Field(
        description="Timestamp at which node execution started, if it has started.",
    )
    completed_at: datetime | None = Field(
        description="Timestamp at which node execution completed, if it has completed.",
    )

    @field_serializer("status")
    def serialize_status(self, status: NodeExecutionStatus) -> str:
        """Return API status values in their documented uppercase form."""

        return _serialize_status(status)


class WorkflowExecutionStatusResponsePayload(BaseModel):
    """Workflow execution status response payload."""

    execution_id: UUID = Field(
        description="Identifier of the workflow execution.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    workflow_id: UUID = Field(
        description="Identifier of the persisted workflow definition.",
        examples=["987e6543-e21b-12d3-a456-426614174000"],
    )
    status: WorkflowExecutionStatus = Field(
        description="Current lifecycle state of the workflow execution.",
        examples=["RUNNING"],
    )
    created_at: datetime = Field(description="Timestamp at which the execution was created.")
    started_at: datetime | None = Field(
        description="Timestamp at which execution began, if it has started.",
    )
    completed_at: datetime | None = Field(
        description="Timestamp at which execution reached a terminal state, if applicable.",
    )
    nodes: list[NodeExecutionStatusResponseItem] = Field(
        description="Persisted status of each node execution in the workflow.",
    )

    @field_serializer("status")
    def serialize_status(self, status: WorkflowExecutionStatus) -> str:
        """Return API status values in their documented uppercase form."""

        return _serialize_status(status)


class WorkflowTriggerResponse(BaseModel):
    """Workflow trigger acknowledgement payload."""

    execution_id: UUID = Field(
        description="Identifier of the execution accepted for asynchronous processing.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    status: WorkflowExecutionStatus = Field(
        description="Execution state after the trigger was accepted.",
        examples=["RUNNING"],
    )


class WorkflowResultNodeResponseItem(BaseModel):
    """Node-level result payload item for completed workflow outputs."""

    node_id: str = Field(description="Identifier of the node that produced this result.")
    status: NodeExecutionStatus = Field(
        description="Final lifecycle state of the node execution.",
        examples=["COMPLETED"],
    )
    output_data: JsonValue = Field(
        description="JSON-compatible output produced by the node.",
        examples=[{"input": {"url": "https://example.test/example-document"}}],
    )
    error_message: str | None = Field(
        description="Human-readable node failure message, if the node failed.",
    )
    error_type: str | None = Field(
        description="Machine-readable node failure type, if the node failed.",
    )
    created_at: datetime = Field(description="Timestamp at which node execution was created.")
    started_at: datetime | None = Field(
        description="Timestamp at which node execution started, if applicable.",
    )
    completed_at: datetime | None = Field(
        description="Timestamp at which node execution completed, if applicable.",
    )

    @field_serializer("status")
    def serialize_status(self, status: NodeExecutionStatus) -> str:
        """Return API status values in their documented uppercase form."""

        return _serialize_status(status)


class WorkflowExecutionResultsResponsePayload(BaseModel):
    """Workflow execution results response payload."""

    execution_id: UUID = Field(
        description="Identifier of the workflow execution.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    workflow_id: UUID = Field(
        description="Identifier of the persisted workflow definition.",
        examples=["987e6543-e21b-12d3-a456-426614174000"],
    )
    status: WorkflowExecutionStatus = Field(
        description="Current lifecycle state of the workflow execution.",
        examples=["COMPLETED"],
    )
    created_at: datetime = Field(description="Timestamp at which the execution was created.")
    started_at: datetime | None = Field(
        description="Timestamp at which execution began, if it has started.",
    )
    completed_at: datetime | None = Field(
        description="Timestamp at which execution reached a terminal state, if applicable.",
    )
    message: str | None = Field(
        default=None,
        description="Result availability or failure message.",
        examples=["Workflow execution is running. Results are not available yet."],
    )
    results: list[WorkflowResultNodeResponseItem] | None = Field(
        default=None,
        description=(
            "Node outputs for a completed execution. Null when final results are unavailable."
        ),
    )

    @field_serializer("status")
    def serialize_status(self, status: WorkflowExecutionStatus) -> str:
        """Return API status values in their documented uppercase form."""

        return _serialize_status(status)
