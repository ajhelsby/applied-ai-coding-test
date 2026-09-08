from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.models.workflow import Workflow
from app.domain.state.states import NodeExecutionStatus
from app.services.workflow_readiness_service import WorkflowReadinessService


class FakeNodeExecutions:
    def __init__(self, statuses: dict[str, NodeExecutionStatus]) -> None:
        self.statuses = dict(statuses)
        self.update_calls: list[tuple[str, NodeExecutionStatus, NodeExecutionStatus]] = []

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        return [
            NodeExecution(
                workflow_execution_id=execution_id,
                node_id=node_id,
                status=status,
            )
            for node_id, status in self.statuses.items()
        ]

    async def update_status_if_current(
        self,
        *,
        node_id: str,
        expected_current_status: NodeExecutionStatus,
        new_status: NodeExecutionStatus,
        **_kwargs: object,
    ) -> bool:
        self.update_calls.append((node_id, expected_current_status, new_status))
        current = self.statuses.get(node_id, NodeExecutionStatus.PENDING)
        if current is not expected_current_status:
            return False
        self.statuses[node_id] = new_status
        return True


class FakeWorkflowExecutions:
    def __init__(self, execution: WorkflowExecution | None) -> None:
        self.execution = execution

    async def get_execution_by_id(self, _execution_id: UUID) -> WorkflowExecution | None:
        return self.execution


class FakeWorkflows:
    def __init__(self, workflow: Workflow | None) -> None:
        self.workflow = workflow

    async def get_workflow_by_id(self, _workflow_id: UUID) -> Workflow | None:
        return self.workflow


class FakeUnitOfWork:
    def __init__(
        self,
        *,
        workflow_execution: WorkflowExecution | None,
        workflow: Workflow | None,
        node_statuses: dict[str, NodeExecutionStatus],
    ) -> None:
        self.workflow_executions = FakeWorkflowExecutions(workflow_execution)
        self.workflows = FakeWorkflows(workflow)
        self.node_executions = FakeNodeExecutions(node_statuses)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeUnitOfWork]:
        yield self


def _workflow(workflow_id: UUID) -> Workflow:
    return Workflow.model_validate(
        {
            "workflow_id": workflow_id,
            "name": "wf",
            "dag": {
                "nodes": [
                    {"id": "a", "handler": "task", "dependencies": []},
                    {"id": "b", "handler": "task", "dependencies": ["a"]},
                    {"id": "c", "handler": "task", "dependencies": ["a"]},
                    {"id": "d", "handler": "task", "dependencies": ["b", "c"]},
                ]
            },
        }
    )


def test_evaluate_promotes_all_currently_ready_nodes() -> None:
    execution = WorkflowExecution(workflow_id=uuid4())
    uow = FakeUnitOfWork(
        workflow_execution=execution,
        workflow=_workflow(execution.workflow_id),
        node_statuses={
            "a": NodeExecutionStatus.COMPLETED,
            "b": NodeExecutionStatus.PENDING,
            "c": NodeExecutionStatus.PENDING,
            "d": NodeExecutionStatus.PENDING,
        },
    )

    decision = asyncio.run(WorkflowReadinessService().evaluate(execution.execution_id, uow))

    assert decision.execution_id == execution.execution_id
    assert decision.ready_node_ids == ("b", "c")
    assert uow.node_executions.statuses["b"] is NodeExecutionStatus.READY
    assert uow.node_executions.statuses["c"] is NodeExecutionStatus.READY
    assert uow.node_executions.statuses["d"] is NodeExecutionStatus.PENDING


def test_evaluate_does_not_reidentify_started_or_processed_nodes() -> None:
    execution = WorkflowExecution(workflow_id=uuid4())
    uow = FakeUnitOfWork(
        workflow_execution=execution,
        workflow=_workflow(execution.workflow_id),
        node_statuses={
            "a": NodeExecutionStatus.COMPLETED,
            "b": NodeExecutionStatus.COMPLETED,
            "c": NodeExecutionStatus.COMPLETED,
            "d": NodeExecutionStatus.PENDING,
        },
    )

    decision = asyncio.run(WorkflowReadinessService().evaluate(execution.execution_id, uow))

    assert decision.ready_node_ids == ("d",)
    assert uow.node_executions.update_calls == [
        ("d", NodeExecutionStatus.PENDING, NodeExecutionStatus.READY)
    ]


def test_evaluate_is_repeatable_and_safe_to_call_multiple_times() -> None:
    execution = WorkflowExecution(workflow_id=uuid4())
    uow = FakeUnitOfWork(
        workflow_execution=execution,
        workflow=_workflow(execution.workflow_id),
        node_statuses={
            "a": NodeExecutionStatus.COMPLETED,
            "b": NodeExecutionStatus.PENDING,
            "c": NodeExecutionStatus.PENDING,
            "d": NodeExecutionStatus.PENDING,
        },
    )

    first = asyncio.run(WorkflowReadinessService().evaluate(execution.execution_id, uow))
    second = asyncio.run(WorkflowReadinessService().evaluate(execution.execution_id, uow))

    assert first.ready_node_ids == ("b", "c")
    assert second.ready_node_ids == ()


def test_evaluate_raises_when_execution_missing() -> None:
    uow = FakeUnitOfWork(
        workflow_execution=None,
        workflow=None,
        node_statuses={},
    )

    with pytest.raises(WorkflowExecutionNotFoundError):
        asyncio.run(WorkflowReadinessService().evaluate(uuid4(), uow))
