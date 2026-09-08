"""Workflow submission HTTP endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.requests import WorkflowSubmissionRequest
from app.api.responses import (
    PersistenceErrorResponse,
    ValidationErrorResponse,
    WorkflowSubmissionResponse,
)
from app.domain.errors.persistence import WorkflowPersistenceError
from app.domain.errors.validation import InvalidWorkflowDefinitionError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.infrastructure.persistence.providers import get_unit_of_work
from app.services.workflow_definition_service import WorkflowDefinitionService

router = APIRouter()
unit_of_work_dependency = Depends(get_unit_of_work)


@router.post(
    "/workflow",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkflowSubmissionResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ValidationErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": PersistenceErrorResponse},
    },
)
async def submit_workflow(
    definition: WorkflowSubmissionRequest,
    unit_of_work: UnitOfWork = unit_of_work_dependency,
) -> WorkflowSubmissionResponse | JSONResponse:
    """Validate and persist a workflow definition."""

    try:
        submission = await WorkflowDefinitionService().submit(definition.model_dump(), unit_of_work)
    except InvalidWorkflowDefinitionError as error:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error_code": "workflow_validation_failed",
                "message": "Workflow definition failed validation.",
                "errors": [asdict(item) for item in error.errors],
            },
        )
    except WorkflowPersistenceError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": "workflow_persistence_failed",
                "message": "Workflow could not be persisted. Please try again later.",
            },
        )
    return WorkflowSubmissionResponse(
        execution_id=submission.execution_id,
        name=submission.name,
        created_at=submission.created_at,
    )
