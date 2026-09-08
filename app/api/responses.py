"""API response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
