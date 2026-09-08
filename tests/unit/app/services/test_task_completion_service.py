from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.models.workflow import Workflow
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.services.node_task_dispatcher import create_task_id
from app.services.task_completion_service import TaskCompletionOutcome, TaskCompletionService


class FakeNodeExecutions:
    def __init__(self, statuses: dict[str, NodeExecutionStatus]) -> None:
        self.statuses = dict(statuses)
        self.outputs: dict[str, dict[str, object]] = {}
        self.errors: dict[str, tuple[str | None, str | None]] = {}

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        return [
            NodeExecution(workflow_execution_id=execution_id, node_id=node_id, status=status)
            for node_id, status in self.statuses.items()
        ]

    async def update_status_if_current(
        self,
        execution_id: UUID,
        node_id: str,
        expected_current_status: NodeExecutionStatus,
        new_status: NodeExecutionStatus,
        *,
        output_data: dict[str, object] | None = None,
        error_message: str | None = None,
        error_type: str | None = None,
        **_kwargs: object,
    ) -> bool:
        del execution_id
        if self.statuses.get(node_id) is not expected_current_status:
            return False
        self.statuses[node_id] = new_status
        if output_data is not None:
            self.outputs[node_id] = output_data
        if error_message is not None or error_type is not None:
            self.errors[node_id] = (error_message, error_type)
        return True


class FakeWorkflowExecutions:
    def __init__(self, execution: WorkflowExecution) -> None:
        self.execution = execution

    async def get_execution_by_id(self, _execution_id: UUID) -> WorkflowExecution:
        return self.execution

    async def update_status_if_current(
        self,
        execution_id: UUID,
        expected_current_status: WorkflowExecutionStatus,
        new_status: WorkflowExecutionStatus,
        **_kwargs: object,
    ) -> bool:
        assert execution_id == self.execution.execution_id
        if self.execution.status is not expected_current_status:
            return False
        self.execution = self.execution.model_copy(update={"status": new_status})
        return True


class FakeWorkflows:
    def __init__(self, workflow: Workflow) -> None:
        self.workflow = workflow

    async def get_workflow_by_id(self, _workflow_id: UUID) -> Workflow:
        return self.workflow


class FakeUnitOfWork:
    def __init__(
        self,
        execution: WorkflowExecution,
        workflow: Workflow,
        node_statuses: dict[str, NodeExecutionStatus],
    ) -> None:
        self.workflow_executions = FakeWorkflowExecutions(execution)
        self.workflows = FakeWorkflows(workflow)
        self.node_executions = FakeNodeExecutions(node_statuses)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeUnitOfWork]:
        yield self


def _workflow(workflow_id: UUID, nodes: list[dict[str, object]]) -> Workflow:
    return Workflow.model_validate(
        {"workflow_id": workflow_id, "name": "wf", "dag": {"nodes": nodes}}
    )


def _event(
    execution_id: UUID,
    node_id: str,
    status: TaskCompletionStatus,
) -> TaskCompletionEvent:
    return TaskCompletionEvent(
        event_id=uuid4(),
        task_id=create_task_id(execution_id, node_id),
        execution_id=execution_id,
        node_id=node_id,
        status=status,
        output_data={"result": "ok"} if status is TaskCompletionStatus.COMPLETED else None,
        error_message="handler failed" if status is TaskCompletionStatus.FAILED else None,
        error_type="RuntimeError" if status is TaskCompletionStatus.FAILED else None,
    )


def test_successful_completion_persists_output_and_promotes_fan_out() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id,
        [
            {"id": "root", "handler": "task", "dependencies": []},
            {"id": "left", "handler": "task", "dependencies": ["root"]},
            {"id": "right", "handler": "task", "dependencies": ["root"]},
        ],
    )
    uow = FakeUnitOfWork(
        execution,
        workflow,
        {
            "root": NodeExecutionStatus.RUNNING,
            "left": NodeExecutionStatus.PENDING,
            "right": NodeExecutionStatus.PENDING,
        },
    )

    decision = asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "root", TaskCompletionStatus.COMPLETED), uow
        )
    )

    assert decision.outcome is TaskCompletionOutcome.PROCESSED
    assert decision.ready_node_ids == ("left", "right")
    assert uow.node_executions.statuses["root"] is NodeExecutionStatus.COMPLETED
    assert uow.node_executions.outputs["root"] == {"result": "ok"}
    assert uow.node_executions.statuses["left"] is NodeExecutionStatus.READY
    assert uow.node_executions.statuses["right"] is NodeExecutionStatus.READY


def test_successful_completion_promotes_fan_in_after_all_parents_finish() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id,
        [
            {"id": "left", "handler": "task", "dependencies": []},
            {"id": "right", "handler": "task", "dependencies": []},
            {"id": "join", "handler": "task", "dependencies": ["left", "right"]},
        ],
    )
    uow = FakeUnitOfWork(
        execution,
        workflow,
        {
            "left": NodeExecutionStatus.RUNNING,
            "right": NodeExecutionStatus.COMPLETED,
            "join": NodeExecutionStatus.PENDING,
        },
    )

    decision = asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "left", TaskCompletionStatus.COMPLETED), uow
        )
    )

    assert decision.ready_node_ids == ("join",)
    assert uow.node_executions.statuses["join"] is NodeExecutionStatus.READY


def test_failed_completion_persists_error_and_fails_workflow() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id,
        [
            {"id": "root", "handler": "task", "dependencies": []},
            {"id": "child", "handler": "task", "dependencies": ["root"]},
        ],
    )
    uow = FakeUnitOfWork(
        execution,
        workflow,
        {"root": NodeExecutionStatus.RUNNING, "child": NodeExecutionStatus.PENDING},
    )

    decision = asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "root", TaskCompletionStatus.FAILED), uow
        )
    )

    assert decision.outcome is TaskCompletionOutcome.PROCESSED
    assert decision.ready_node_ids == ()
    assert uow.node_executions.statuses["root"] is NodeExecutionStatus.FAILED
    assert uow.node_executions.errors["root"] == ("handler failed", "RuntimeError")
    assert uow.node_executions.statuses["child"] is NodeExecutionStatus.PENDING
    assert uow.workflow_executions.execution.status is WorkflowExecutionStatus.FAILED


def test_duplicate_completion_is_a_no_op() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id, [{"id": "node", "handler": "task", "dependencies": []}]
    )
    uow = FakeUnitOfWork(execution, workflow, {"node": NodeExecutionStatus.COMPLETED})

    decision = asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "node", TaskCompletionStatus.COMPLETED), uow
        )
    )

    assert decision.outcome is TaskCompletionOutcome.DUPLICATE
    assert decision.ready_node_ids == ()
    assert uow.node_executions.outputs == {}


def test_final_successful_node_completes_workflow() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id, [{"id": "node", "handler": "task", "dependencies": []}]
    )
    uow = FakeUnitOfWork(execution, workflow, {"node": NodeExecutionStatus.RUNNING})

    asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "node", TaskCompletionStatus.COMPLETED), uow
        )
    )

    assert uow.workflow_executions.execution.status is WorkflowExecutionStatus.COMPLETED
