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


def test_get_workflow_execution_returns_running_execution_with_node_states() -> None:
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.RUNNING,
    )
    node_executions = [
        NodeExecution(
            workflow_execution_id=execution.execution_id,
            node_id=status.value,
            status=status,
        )
        for status in NodeExecutionStatus
    ]
    unit_of_work = InMemoryUnitOfWork([execution], node_executions)
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_id"] == str(execution.execution_id)
    assert payload["workflow_id"] == str(execution.workflow_id)
    assert payload["status"] == "RUNNING"
    assert datetime.fromisoformat(payload["created_at"]) == execution.created_at
    assert payload["started_at"] is None
    assert payload["completed_at"] is None
    returned_node_statuses = {node["node_id"]: node["status"] for node in payload["nodes"]}
    expected_node_statuses = {
        node_execution.node_id: node_execution.status.value.upper()
        for node_execution in node_executions
    }
    assert returned_node_statuses == expected_node_statuses


def test_get_workflow_execution_returns_not_found_for_unknown_execution() -> None:
    unit_of_work = InMemoryUnitOfWork([], [])
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow execution not found."


def test_get_workflow_execution_does_not_modify_persisted_state() -> None:
    execution = WorkflowExecution(
        workflow_id=uuid4(),
        status=WorkflowExecutionStatus.COMPLETED,
    )
    node_execution = NodeExecution(
        workflow_execution_id=execution.execution_id,
        node_id="completed-node",
        status=NodeExecutionStatus.COMPLETED,
    )
    unit_of_work = InMemoryUnitOfWork([execution], [node_execution])
    executions_before = list(unit_of_work.workflow_executions.executions)
    nodes_before = list(unit_of_work.node_executions.node_executions)
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.get(f"/workflows/{execution.execution_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert unit_of_work.workflow_executions.executions == executions_before
    assert unit_of_work.node_executions.node_executions == nodes_before
