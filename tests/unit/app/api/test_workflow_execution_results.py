from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.main import app
from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.infrastructure.persistence.providers import get_unit_of_work


class InMemoryWorkflowExecutionRepository:
    def __init__(self, executions: list[WorkflowExecution]) -> None:
        self.executions = executions

    async def get_execution_by_id(self, execution_id: UUID) -> WorkflowExecution | None:
        return next(
            (execution for execution in self.executions if execution.execution_id == execution_id),
            None,
        )


class InMemoryNodeExecutionRepository:
    def __init__(self, node_executions: list[NodeExecution]) -> None:
        self.node_executions = node_executions

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        return [
            node_execution
            for node_execution in self.node_executions
            if node_execution.workflow_execution_id == execution_id
        ]


class InMemoryUnitOfWork:
    def __init__(
        self,
        executions: list[WorkflowExecution],
        node_executions: list[NodeExecution],
    ) -> None:
        self.workflow_executions = InMemoryWorkflowExecutionRepository(executions)
        self.node_executions = InMemoryNodeExecutionRepository(node_executions)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[InMemoryUnitOfWork]:
        yield self


client = TestClient(app)


def test_get_workflow_execution_results_returns_aggregated_output_for_completed_execution() -> None:
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.COMPLETED,
    )
    completed_node = NodeExecution(
        workflow_execution_id=execution.execution_id,
        node_id="node-completed",
        status=NodeExecutionStatus.COMPLETED,
        output_data={"result": "ok"},
    )
    non_completed_node = NodeExecution(
        workflow_execution_id=execution.execution_id,
        node_id="node-skipped",
        status=NodeExecutionStatus.SKIPPED,
        output_data={"result": "ignored"},
    )
    unit_of_work = InMemoryUnitOfWork([execution], [completed_node, non_completed_node])
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_id"] == str(execution.execution_id)
    assert payload["workflow_id"] == str(execution.workflow_id)
    assert payload["status"] == "COMPLETED"
    assert datetime.fromisoformat(payload["created_at"]) == execution.created_at
    assert payload["message"] is None
    assert payload["results"] is not None
    assert len(payload["results"]) == 1
    assert payload["results"][0]["node_id"] == "node-completed"
    assert payload["results"][0]["status"] == "COMPLETED"
    assert payload["results"][0]["output_data"] == {"result": "ok"}


def test_get_workflow_execution_results_returns_pending_without_results() -> None:
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.PENDING,
    )
    unit_of_work = InMemoryUnitOfWork([execution], [])
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PENDING"
    assert payload["results"] is None
    assert payload["message"] == "Workflow execution is pending. Results are not available yet."


def test_get_workflow_execution_results_returns_running_without_results() -> None:
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.RUNNING,
    )
    unit_of_work = InMemoryUnitOfWork([execution], [])
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "RUNNING"
    assert payload["results"] is None
    assert payload["message"] == "Workflow execution is running. Results are not available yet."


def test_get_workflow_execution_results_returns_failed_without_results() -> None:
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.FAILED,
    )
    unit_of_work = InMemoryUnitOfWork([execution], [])
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "FAILED"
    assert payload["results"] is None
    assert payload["message"] == "Workflow execution failed. Final results are not available."


def test_get_workflow_execution_results_returns_no_results_for_inconsistent_completed_state() -> (
    None
):
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.COMPLETED,
    )
    failed_node = NodeExecution(
        workflow_execution_id=execution.execution_id,
        node_id="failed-node",
        status=NodeExecutionStatus.FAILED,
        output_data={"result": "bad"},
        error_message="boom",
        error_type="RuntimeError",
    )
    unit_of_work = InMemoryUnitOfWork([execution], [failed_node])
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["results"] is None
    assert payload["message"] == (
        "Workflow execution state is inconsistent: completed execution contains failed node "
        "executions. Final results are not available."
    )


def test_get_workflow_execution_results_returns_not_found_for_unknown_execution() -> None:
    unit_of_work = InMemoryUnitOfWork([], [])
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{uuid4()}/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow execution not found."


def test_get_workflow_execution_results_does_not_modify_persisted_state() -> None:
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.COMPLETED,
    )
    node_execution = NodeExecution(
        workflow_execution_id=execution.execution_id,
        node_id="completed-node",
        status=NodeExecutionStatus.COMPLETED,
        output_data={"result": True},
    )
    unit_of_work = InMemoryUnitOfWork([execution], [node_execution])
    executions_before = list(unit_of_work.workflow_executions.executions)
    nodes_before = list(unit_of_work.node_executions.node_executions)
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert unit_of_work.workflow_executions.executions == executions_before
    assert unit_of_work.node_executions.node_executions == nodes_before
