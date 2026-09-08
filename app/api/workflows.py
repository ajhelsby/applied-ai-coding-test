"""Workflow submission HTTP endpoints."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.infrastructure.persistence.providers import get_unit_of_work
from app.services.workflow_definition_service import WorkflowDefinitionService
from app.services.workflow_execution_status_service import WorkflowExecutionStatusService
from app.services.workflow_trigger_service import WorkflowTriggerService

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


@router.get(
    "/workflows/{execution_id}/results",
    response_model=WorkflowExecutionResultsResponsePayload,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Workflow execution not found."}},
)
async def get_workflow_execution_results(
    execution_id: UUID,
    unit_of_work: UnitOfWork = unit_of_work_dependency,
) -> WorkflowExecutionResultsResponsePayload:
    """Retrieve final aggregated node outputs for a workflow execution.

    Invariant: if any node execution fails, the workflow execution status is FAILED.
    Therefore, COMPLETED is treated as successful completion for final results.
    A defensive guard still checks for inconsistent persisted state.
    """

    result = await WorkflowExecutionStatusService().get(execution_id, unit_of_work)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow execution not found.",
        )

    execution = result.execution
    if execution.status is WorkflowExecutionStatus.PENDING:
        return WorkflowExecutionResultsResponsePayload(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            message="Workflow execution is pending. Results are not available yet.",
            results=None,
        )
    if execution.status is WorkflowExecutionStatus.RUNNING:
        return WorkflowExecutionResultsResponsePayload(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            message="Workflow execution is running. Results are not available yet.",
            results=None,
        )
    if execution.status is WorkflowExecutionStatus.FAILED:
        return WorkflowExecutionResultsResponsePayload(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            message="Workflow execution failed. Final results are not available.",
            results=None,
        )
    if any(
        node_execution.status is NodeExecutionStatus.FAILED
        for node_execution in result.node_executions
    ):
        return WorkflowExecutionResultsResponsePayload(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            message=(
                "Workflow execution state is inconsistent: completed execution contains "
                "failed node executions. Final results are not available."
            ),
            results=None,
        )

    return WorkflowExecutionResultsResponsePayload(
        execution_id=execution.execution_id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        created_at=execution.created_at,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        message=None,
        results=[
            WorkflowResultNodeResponseItem(
                node_id=node_execution.node_id,
                status=node_execution.status,
                output_data=node_execution.output_data,
                error_message=node_execution.error_message,
                error_type=node_execution.error_type,
                created_at=node_execution.created_at,
                started_at=node_execution.started_at,
                completed_at=node_execution.completed_at,
            )
            for node_execution in result.node_executions
            if node_execution.status is NodeExecutionStatus.COMPLETED
        ],
    )


@router.get(
    "/workflows/{execution_id}",
    response_model=WorkflowExecutionStatusResponsePayload,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Workflow execution not found."}},
)
async def get_workflow_execution(
    execution_id: UUID,
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
    response_model=WorkflowTriggerResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": PersistenceErrorResponse},
    },
)
async def trigger_workflow_execution(
    execution_id: UUID,
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
