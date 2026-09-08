from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.main import app
from app.domain.errors.persistence import WorkflowPersistenceError
from app.domain.models.execution import WorkflowExecution
from app.domain.models.workflow import Workflow
from app.domain.state.states import WorkflowExecutionStatus
from app.infrastructure.persistence.providers import get_unit_of_work
from app.services.workflow_definition_service import WorkflowDefinitionService


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


class FailingWorkflowRepository(InMemoryWorkflowRepository):
    async def create_workflow(self, workflow: Workflow) -> Workflow:
        del workflow
        raise WorkflowPersistenceError("Database unavailable")


class InMemoryWorkflowExecutionRepository:
    def __init__(self) -> None:
        self.executions: list[WorkflowExecution] = []

    async def create_execution(self, execution: WorkflowExecution) -> WorkflowExecution:
        self.executions.append(execution)
        return execution

    async def get_execution_by_id(self, execution_id: UUID) -> WorkflowExecution | None:
        return next(
            (execution for execution in self.executions if execution.execution_id == execution_id),
            None,
        )

    async def update_status_if_current(
        self,
        execution_id: UUID,
        expected_current_status: WorkflowExecutionStatus,
        new_status: WorkflowExecutionStatus,
        *,
        started_at: object | None = None,
        completed_at: object | None = None,
        input_data: dict[str, object] | None = None,
    ) -> bool:
        del completed_at
        for index, execution in enumerate(self.executions):
            if (
                execution.execution_id == execution_id
                and execution.status == expected_current_status
            ):
                updates: dict[str, object] = {"status": new_status}
                if started_at is not None:
                    updates["started_at"] = started_at
                if input_data is not None:
                    updates["input_data"] = input_data
                self.executions[index] = execution.model_copy(update=updates)
                return True
        return False


class InMemoryOutboxRepository:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def add_execution_triggered(self, execution_id: UUID) -> None:
        self.events.append(execution_id)


class FailingOutboxRepository(InMemoryOutboxRepository):
    async def add_execution_triggered(self, execution_id: UUID) -> None:
        del execution_id
        raise WorkflowPersistenceError("Outbox unavailable")


class InMemoryUnitOfWork:
    def __init__(self) -> None:
        self.workflows = InMemoryWorkflowRepository()
        self.workflow_executions = InMemoryWorkflowExecutionRepository()
        self.outbox_events = InMemoryOutboxRepository()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["InMemoryUnitOfWork"]:
        yield self


class FailingUnitOfWork(InMemoryUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self.workflows = FailingWorkflowRepository()


class FailingOutboxUnitOfWork(InMemoryUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self.outbox_events = FailingOutboxRepository()


client = TestClient(app)


def test_submit_workflow_persists_definition_without_creating_an_execution() -> None:
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
    assert response.json()["name"] == "workflow"
    assert response.json()["created_at"]
    assert len(unit_of_work.workflows.workflows) == 1
    assert len(unit_of_work.workflow_executions.executions) == 0


def test_build_dag_returns_validated_traversal_graph() -> None:
    dag = WorkflowDefinitionService().build_dag(
        {
            "name": "workflow",
            "dag": {
                "nodes": [
                    {"id": "input", "handler": "input", "dependencies": []},
                    {"id": "output", "handler": "output", "dependencies": ["input"]},
                ]
            },
        }
    )

    assert tuple(node.node_id for node in dag.get_roots()) == ("input",)
    assert tuple(node.node_id for node in dag.get_terminals()) == ("output",)


def test_submit_workflow_returns_all_validation_errors() -> None:
    unit_of_work = InMemoryUnitOfWork()
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
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
    assert [error["code"] for error in response.json()["errors"]] == [
        "required_workflow_name",
        "invalid_handler_config",
        "unknown_dependency",
    ]
    assert len(unit_of_work.workflows.workflows) == 0


def test_submit_workflow_returns_service_unavailable_when_persistence_fails() -> None:
    app.dependency_overrides[get_unit_of_work] = FailingUnitOfWork
    try:
        response = client.post(
            "/workflow",
            json={"name": "workflow", "dag": {"nodes": []}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error_code"] == "workflow_persistence_failed"


def test_submit_workflow_rejects_malformed_request_payload() -> None:
    app.dependency_overrides[get_unit_of_work] = lambda: InMemoryUnitOfWork()
    try:
        response = client.post(
            "/workflow",
            json={"dag": {"nodes": []}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_submit_workflow_rejects_unexpected_top_level_fields() -> None:
    app.dependency_overrides[get_unit_of_work] = lambda: InMemoryUnitOfWork()
    try:
        response = client.post(
            "/workflow",
            json={"name": "workflow", "dag": {"nodes": []}, "unknown_field": "nope"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_trigger_workflow_returns_running_status_for_pending_execution() -> None:
    execution = WorkflowExecution(workflow_id=Workflow(name="workflow").workflow_id)
    unit_of_work = InMemoryUnitOfWork()
    unit_of_work.workflow_executions.executions.append(execution)
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.post(f"/workflow/trigger/{execution.execution_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["execution_id"] == str(execution.execution_id)
    assert response.json()["status"] == "running"
    assert unit_of_work.workflow_executions.executions[0].status == WorkflowExecutionStatus.RUNNING
    assert unit_of_work.outbox_events.events == [execution.execution_id]


def test_trigger_workflow_persists_input_parameters() -> None:
    execution = WorkflowExecution(workflow_id=Workflow(name="workflow").workflow_id)
    unit_of_work = InMemoryUnitOfWork()
    unit_of_work.workflow_executions.executions.append(execution)
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.post(
            f"/workflow/trigger/{execution.execution_id}",
            json={"input": {"document_id": "doc-123", "options": {"draft": True}}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert unit_of_work.workflow_executions.executions[0].input_data == {
        "document_id": "doc-123",
        "options": {"draft": True},
    }


def test_trigger_workflow_returns_not_found_for_unknown_execution() -> None:
    unit_of_work = InMemoryUnitOfWork()
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.post("/workflow/trigger/00000000-0000-0000-0000-000000000000")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error_code"] == "workflow_execution_not_found"


def test_trigger_workflow_rejects_non_pending_execution() -> None:
    execution = WorkflowExecution(
        workflow_id=Workflow(name="workflow").workflow_id,
        status=WorkflowExecutionStatus.COMPLETED,
    )
    unit_of_work = InMemoryUnitOfWork()
    unit_of_work.workflow_executions.executions.append(execution)
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.post(f"/workflow/trigger/{execution.execution_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "workflow_execution_not_triggerable"
    assert unit_of_work.outbox_events.events == []


def test_trigger_workflow_returns_service_unavailable_when_outbox_write_fails() -> None:
    execution = WorkflowExecution(workflow_id=Workflow(name="workflow").workflow_id)
    unit_of_work = FailingOutboxUnitOfWork()
    unit_of_work.workflow_executions.executions.append(execution)
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    try:
        response = client.post(f"/workflow/trigger/{execution.execution_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error_code"] == "workflow_trigger_persistence_failed"
