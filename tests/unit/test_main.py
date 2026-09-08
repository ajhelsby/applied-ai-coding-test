from contextlib import asynccontextmanager
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.workflows import get_unit_of_work
from app.domain.models.execution import WorkflowExecution
from app.domain.models.workflow import Workflow


class InMemoryWorkflowRepository:
    def __init__(self) -> None:
        self.workflows: list[Workflow] = []

    async def create_workflow(self, workflow: Workflow) -> Workflow:
        self.workflows.append(workflow)
        return workflow

    async def get_workflow_by_id(self, workflow_id: UUID) -> Workflow | None:
        return next(
            (workflow for workflow in self.workflows if workflow.workflow_id == workflow_id),
            None,
        )


class InMemoryWorkflowExecutionRepository:
    def __init__(self) -> None:
        self.executions: list[WorkflowExecution] = []

    async def create_execution(self, execution: WorkflowExecution) -> WorkflowExecution:
        self.executions.append(execution)
        return execution


class InMemoryUnitOfWork:
    def __init__(self) -> None:
        self.workflows = InMemoryWorkflowRepository()
        self.workflow_executions = InMemoryWorkflowExecutionRepository()

    @asynccontextmanager
    async def transaction(self):
        yield self


client = TestClient(app)


def test_root_returns_ok_status() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_healthy_status() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_submit_workflow_returns_execution_id_for_valid_definition() -> None:
    unit_of_work = InMemoryUnitOfWork()
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.post(
            "/workflow",
            json={
                "name": "workflow",
                "dag": {
                    "nodes": [
                        {"id": "input", "handler": "input", "dependencies": []},
                        {
                            "id": "fetch",
                            "handler": "call_external_service",
                            "dependencies": ["input"],
                            "config": {"url": "https://example.test"},
                        },
                    ]
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert UUID(response.json()["execution_id"])
    assert len(unit_of_work.workflows.workflows) == 1
    assert len(unit_of_work.workflow_executions.executions) == 1


def test_submit_workflow_returns_all_validation_errors() -> None:
    app.dependency_overrides[get_unit_of_work] = lambda: InMemoryUnitOfWork()
    try:
        response = client.post(
            "/workflow",
            json={
                "name": "",
                "dag": {
                    "nodes": [
                        {
                            "id": "fetch",
                            "handler": "call_external_service",
                            "dependencies": ["unknown"],
                        }
                    ]
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert [error["code"] for error in response.json()["detail"]["errors"]] == [
        "required_workflow_name",
        "invalid_handler_config",
        "unknown_dependency",
    ]
