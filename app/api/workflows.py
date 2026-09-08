"""Workflow submission HTTP endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.domain.errors.validation import InvalidWorkflowDefinitionError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.infrastructure.persistence.providers import get_unit_of_work
from app.services.workflow_definition_service import WorkflowDefinitionService

router = APIRouter()
unit_of_work_dependency = Depends(get_unit_of_work)


@router.post("/workflow", status_code=status.HTTP_201_CREATED)
async def submit_workflow(
    definition: dict[str, Any],
    unit_of_work: UnitOfWork = unit_of_work_dependency,
) -> dict[str, str]:
    """Validate, persist, and create a pending execution for a workflow."""

    try:
        execution = await WorkflowDefinitionService().submit(definition, unit_of_work)
    except InvalidWorkflowDefinitionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"errors": [asdict(item) for item in error.errors]},
        ) from error
    return {"execution_id": str(execution.execution_id)}
