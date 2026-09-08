"""API response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus


def _serialize_status(status: StrEnum) -> str:
    """Return persisted status values in their documented API form."""

    return status.value.upper()


class WorkflowSubmissionResponse(BaseModel):
    """Workflow submission success response payload."""

    execution_id: UUID
    name: str
    created_at: datetime


class ValidationErrorItemResponse(BaseModel):
    """Structured validation failure item."""

    code: str
    message: str
    path: str
    node_id: str | None = None
    dependency_id: str | None = None
    meta: dict[str, str] = Field(default_factory=dict)


class ValidationErrorResponse(BaseModel):
    """Structured domain validation failure response payload."""

    error_code: str
    message: str
    errors: list[ValidationErrorItemResponse]


class PersistenceErrorResponse(BaseModel):
    """Workflow persistence failure response payload."""

    error_code: str
    message: str


class NodeExecutionStatusResponseItem(BaseModel):
    """Node execution status payload item."""

    node_id: str
    status: NodeExecutionStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @field_serializer("status")
    def serialize_status(self, status: NodeExecutionStatus) -> str:
        """Return API status values in their documented uppercase form."""

        return _serialize_status(status)


class WorkflowExecutionStatusResponsePayload(BaseModel):
    """Workflow execution status response payload."""

    execution_id: UUID
    workflow_id: UUID
    status: WorkflowExecutionStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    nodes: list[NodeExecutionStatusResponseItem]

    @field_serializer("status")
    def serialize_status(self, status: WorkflowExecutionStatus) -> str:
        """Return API status values in their documented uppercase form."""

        return _serialize_status(status)


class WorkflowTriggerResponse(BaseModel):
    """Workflow trigger acknowledgement payload."""

    execution_id: UUID
    status: WorkflowExecutionStatus
