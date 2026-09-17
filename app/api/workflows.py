"""Workflow submission HTTP endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import JSONResponse

from app.api.requests import WorkflowSubmissionRequest, WorkflowTriggerRequest
from app.api.responses import (
    NodeExecutionStatusResponseItem,
    PersistenceErrorResponse,
    ValidationErrorResponse,
    WorkflowExecutionResultsResponsePayload,
    WorkflowExecutionStatusResponsePayload,
    WorkflowResultNodeResponseItem,
    WorkflowSubmissionResponse,
    WorkflowTriggerResponse,
)
from app.domain.errors.persistence import WorkflowPersistenceError
from app.domain.errors.transitions import (
    WorkflowExecutionNotFoundError,
    WorkflowExecutionNotTriggerableError,
)
from app.domain.errors.validation import InvalidWorkflowDefinitionError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.infrastructure.persistence.providers import get_unit_of_work
from app.services.workflow_definition_service import WorkflowDefinitionService
from app.services.workflow_execution_results_service import WorkflowExecutionResultsService
from app.services.workflow_execution_status_service import WorkflowExecutionStatusService
from app.services.workflow_trigger_service import WorkflowTriggerService

router = APIRouter()
unit_of_work_dependency = Depends(get_unit_of_work)


@router.post(
    "/workflow",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a workflow definition",
    description=(
        "Validate and persist a workflow definition together with a pending execution. "
        "Submission is synchronous and does not start execution; call the trigger endpoint "
        "to begin asynchronous processing."
    ),
    response_description="The accepted workflow and its pending execution identifier.",
    response_model=WorkflowSubmissionResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ValidationErrorResponse,
            "description": "The workflow definition failed validation.",
            "content": {
                "application/json": {
                    "example": {
                        "error_code": "workflow_validation_failed",
                        "message": "Workflow definition failed validation.",
                        "errors": [
                            {
                                "code": "unknown_dependency",
                                "message": "Node 'fetch' references unknown dependency 'missing'.",
                                "path": "dag.nodes[0].dependencies[0]",
                                "node_id": "fetch",
                                "dependency_id": "missing",
                                "meta": {},
                            }
                        ],
                    }
                }
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": PersistenceErrorResponse,
            "description": "The workflow could not be persisted.",
        },
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


@router.get(
    "/workflows/{execution_id}/results",
    summary="Retrieve workflow results",
    description=(
        "Retrieve persisted node outputs for a workflow execution. Results are available "
        "only after successful completion; pending, running, and failed executions return "
        "a status and explanatory message without final results."
    ),
    response_description="The workflow execution state and available persisted results.",
    response_model=WorkflowExecutionResultsResponsePayload,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "The workflow execution was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Workflow execution not found.",
                    }
                }
            },
        }
    },
)
async def get_workflow_execution_results(
    execution_id: Annotated[
        UUID,
        Path(description="UUID of the workflow execution whose results should be retrieved."),
    ],
    unit_of_work: UnitOfWork = unit_of_work_dependency,
) -> WorkflowExecutionResultsResponsePayload:
    """Retrieve final aggregated node outputs for a workflow execution."""

    result = await WorkflowExecutionResultsService().get(execution_id, unit_of_work)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow execution not found.",
        )

    execution = result.execution
    return WorkflowExecutionResultsResponsePayload(
        execution_id=execution.execution_id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        created_at=execution.created_at,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        message=result.message,
        results=None
        if result.results is None
        else [
            WorkflowResultNodeResponseItem(
                node_id=node_result.node_id,
                status=node_result.status,
                output_data=node_result.output_data,
                error_message=node_result.error_message,
                error_type=node_result.error_type,
                created_at=node_result.created_at,
                started_at=node_result.started_at,
                completed_at=node_result.completed_at,
            )
            for node_result in result.results
        ],
    )


@router.get(
    "/workflows/{execution_id}",
    summary="Retrieve workflow execution status",
    description=(
        "Retrieve the current persisted status of a workflow execution and each of its "
        "nodes. This operation is read-only and never starts or advances execution."
    ),
    response_description="The current workflow and node execution statuses.",
    response_model=WorkflowExecutionStatusResponsePayload,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "The workflow execution was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Workflow execution not found.",
                    }
                }
            },
        }
    },
)
async def get_workflow_execution(
    execution_id: Annotated[
        UUID,
        Path(description="UUID of the workflow execution whose status should be retrieved."),
    ],
    unit_of_work: UnitOfWork = unit_of_work_dependency,
) -> WorkflowExecutionStatusResponsePayload:
    """Retrieve the current persisted status of a workflow execution."""

    result = await WorkflowExecutionStatusService().get(execution_id, unit_of_work)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow execution not found.",
        )

    execution = result.execution
    return WorkflowExecutionStatusResponsePayload(
        execution_id=execution.execution_id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        created_at=execution.created_at,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        nodes=[
            NodeExecutionStatusResponseItem(
                node_id=node_execution.node_id,
                status=node_execution.status,
                created_at=node_execution.created_at,
                started_at=node_execution.started_at,
                completed_at=node_execution.completed_at,
            )
            for node_execution in result.node_executions
        ],
    )


@router.post(
    "/workflow/trigger/{execution_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a workflow execution",
    description=(
        "Accept a trigger for an existing pending workflow execution, persist its input, and "
        "queue asynchronous processing. The 202 response acknowledges acceptance and does "
        "not indicate that execution has completed."
    ),
    response_description="The synchronous acknowledgement for the accepted trigger.",
    response_model=WorkflowTriggerResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": PersistenceErrorResponse,
            "description": "The workflow execution was not found.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "The execution cannot be triggered or the request is invalid.",
            "content": {
                "application/json": {
                    "example": {
                        "error_code": "workflow_execution_not_triggerable",
                        "message": (
                            "Workflow execution cannot be triggered from its current state."
                        ),
                    }
                }
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": PersistenceErrorResponse,
            "description": "The trigger could not be persisted.",
        },
    },
)
async def trigger_workflow_execution(
    execution_id: Annotated[
        UUID,
        Path(description="UUID of the pending workflow execution to trigger."),
    ],
    trigger: WorkflowTriggerRequest | None = None,
    unit_of_work: UnitOfWork = unit_of_work_dependency,
) -> WorkflowTriggerResponse | JSONResponse:
    """Accept a trigger request for an existing workflow execution."""

    try:
        trigger_decision = await WorkflowTriggerService().trigger(
            execution_id=execution_id,
            input_data=trigger.input if trigger is not None else None,
            unit_of_work=unit_of_work,
        )
    except WorkflowExecutionNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error_code": "workflow_execution_not_found",
                "message": "Workflow execution was not found.",
            },
        )
    except WorkflowExecutionNotTriggerableError:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error_code": "workflow_execution_not_triggerable",
                "message": "Workflow execution cannot be triggered from its current state.",
            },
        )
    except WorkflowPersistenceError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": "workflow_trigger_persistence_failed",
                "message": "Workflow trigger could not be accepted. Please try again later.",
            },
        )

    return WorkflowTriggerResponse(
        execution_id=trigger_decision.execution_id,
        status=trigger_decision.status,
    )
