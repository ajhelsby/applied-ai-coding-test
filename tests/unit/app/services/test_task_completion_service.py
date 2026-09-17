from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.models.json import JsonValue
from app.domain.models.workflow import Workflow
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.services.node_task_dispatcher import create_task_id
from app.services.task_completion_service import (
    TaskCompletionDecision,
    TaskCompletionOutcome,
    TaskCompletionService,
)


class FakeNodeExecutions:
    def __init__(self, statuses: dict[str, NodeExecutionStatus]) -> None:
        self.statuses = dict(statuses)
        self.outputs: dict[str, JsonValue] = {}
        self.errors: dict[str, tuple[str | None, str | None]] = {}
        self.fail_updates = False

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        return [
            NodeExecution(
                workflow_execution_id=execution_id,
                node_id=node_id,
                status=status,
                output_data=self.outputs.get(node_id, {}),
                error_message=self.errors.get(node_id, (None, None))[0],
                error_type=self.errors.get(node_id, (None, None))[1],
            )
            for node_id, status in self.statuses.items()
        ]

    async def update_status_if_current(
        self,
        execution_id: UUID,
        node_id: str,
        expected_current_status: NodeExecutionStatus,
        new_status: NodeExecutionStatus,
        *,
        output_data: JsonValue = None,
        error_message: str | None = None,
        error_type: str | None = None,
        **_kwargs: object,
    ) -> bool:
        del execution_id
        if self.fail_updates:
            raise RuntimeError("node persistence failed")
        if self.statuses.get(node_id) is not expected_current_status:
            return False
        self.statuses[node_id] = new_status
        self.outputs[node_id] = output_data
        if error_message is not None or error_type is not None:
            self.errors[node_id] = (error_message, error_type)
        return True

    async def claim_pending_nodes(
        self,
        execution_id: UUID,
        node_ids: Sequence[str],
    ) -> tuple[str, ...]:
        claimed_ids = tuple(
            node_id
            for node_id in node_ids
            if self.statuses.get(node_id) is NodeExecutionStatus.PENDING
        )
        return claimed_ids

    async def fail_pending_nodes(
        self,
        _execution_id: UUID,
        node_ids: Sequence[str],
        *,
        reason: str,
        completed_at: object,
    ) -> tuple[str, ...]:
        del completed_at
        skipped_ids = tuple(
            node_id
            for node_id in node_ids
            if self.statuses.get(node_id) is NodeExecutionStatus.PENDING
        )
        for node_id in skipped_ids:
            self.statuses[node_id] = NodeExecutionStatus.FAILED
            self.errors[node_id] = (reason, "FailedDependency")
        return skipped_ids


class FakeWorkflowExecutions:
    def __init__(self, execution: WorkflowExecution) -> None:
        self.execution = execution
        self.completion_lock = asyncio.Lock()

    async def get_execution_by_id(self, _execution_id: UUID) -> WorkflowExecution:
        return self.execution

    async def get_execution_by_id_for_update(self, _execution_id: UUID) -> WorkflowExecution:
        await self.completion_lock.acquire()
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


class FakeOutboxEvents:
    async def add_message(
        self,
        *,
        message_id: UUID,
        message_type: str,
        target_stream: str,
        payload: dict[str, object],
        aggregate_id: UUID | None = None,
    ) -> None:
        del message_id, message_type, target_stream, payload, aggregate_id


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
        self.outbox_events = FakeOutboxEvents()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeUnitOfWork]:
        try:
            yield self
        finally:
            if self.workflow_executions.completion_lock.locked():
                self.workflow_executions.completion_lock.release()


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
    assert uow.node_executions.statuses["left"] is NodeExecutionStatus.PENDING
    assert uow.node_executions.statuses["right"] is NodeExecutionStatus.PENDING


def test_successful_completion_persists_null_output() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id, [{"id": "node", "handler": "task", "dependencies": []}]
    )
    uow = FakeUnitOfWork(execution, workflow, {"node": NodeExecutionStatus.RUNNING})

    decision = asyncio.run(
        TaskCompletionService().process(
            TaskCompletionEvent(
                event_id=uuid4(),
                task_id=create_task_id(execution.execution_id, "node"),
                execution_id=execution.execution_id,
                node_id="node",
                status=TaskCompletionStatus.COMPLETED,
                output_data=None,
            ),
            uow,
        )
    )

    assert decision.outcome is TaskCompletionOutcome.PROCESSED
    assert uow.node_executions.statuses["node"] is NodeExecutionStatus.COMPLETED
    assert uow.node_executions.outputs["node"] is None


def test_fan_out_terminal_branches_complete_workflow() -> None:
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

    root_decision = asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "root", TaskCompletionStatus.COMPLETED), uow
        )
    )
    assert root_decision.ready_node_ids == ("left", "right")

    uow.node_executions.statuses["left"] = NodeExecutionStatus.RUNNING
    uow.node_executions.statuses["right"] = NodeExecutionStatus.RUNNING

    async def complete_terminal_branches() -> list[TaskCompletionDecision]:
        decisions = await asyncio.gather(
            TaskCompletionService().process(
                _event(execution.execution_id, "left", TaskCompletionStatus.COMPLETED), uow
            ),
            TaskCompletionService().process(
                _event(execution.execution_id, "right", TaskCompletionStatus.COMPLETED), uow
            ),
        )
        return list(decisions)

    asyncio.run(complete_terminal_branches())

    assert uow.workflow_executions.execution.status is WorkflowExecutionStatus.COMPLETED


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
    assert uow.node_executions.statuses["join"] is NodeExecutionStatus.PENDING


def test_concurrent_parent_completions_promote_fan_in_only_once() -> None:
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
            "right": NodeExecutionStatus.RUNNING,
            "join": NodeExecutionStatus.PENDING,
        },
    )

    async def complete_both_parents() -> list[TaskCompletionDecision]:
        decisions = await asyncio.gather(
            TaskCompletionService().process(
                _event(execution.execution_id, "left", TaskCompletionStatus.COMPLETED), uow
            ),
            TaskCompletionService().process(
                _event(execution.execution_id, "right", TaskCompletionStatus.COMPLETED), uow
            ),
        )
        return list(decisions)

    decisions = asyncio.run(complete_both_parents())

    assert sorted(decision.ready_node_ids for decision in decisions) == [(), ("join",)]
    assert uow.node_executions.statuses["join"] is NodeExecutionStatus.PENDING


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
    assert uow.node_executions.outputs["root"] is None
    assert uow.node_executions.errors["root"] == ("handler failed", "RuntimeError")
    assert uow.node_executions.statuses["child"] is NodeExecutionStatus.FAILED
    assert uow.node_executions.errors["child"] == (
        "Dependency 'root' failed.",
        "FailedDependency",
    )
    assert uow.workflow_executions.execution.status is WorkflowExecutionStatus.FAILED


def test_failed_completion_skips_multi_level_dependants_and_preserves_independent_nodes() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id,
        [
            {"id": "root", "handler": "task", "dependencies": []},
            {"id": "left", "handler": "task", "dependencies": ["root"]},
            {"id": "right", "handler": "task", "dependencies": ["root"]},
            {"id": "join", "handler": "task", "dependencies": ["left", "right"]},
            {"id": "independent", "handler": "task", "dependencies": []},
        ],
    )
    uow = FakeUnitOfWork(
        execution,
        workflow,
        {
            "root": NodeExecutionStatus.RUNNING,
            "left": NodeExecutionStatus.PENDING,
            "right": NodeExecutionStatus.PENDING,
            "join": NodeExecutionStatus.PENDING,
            "independent": NodeExecutionStatus.PENDING,
        },
    )

    asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "root", TaskCompletionStatus.FAILED), uow
        )
    )

    assert uow.node_executions.statuses == {
        "root": NodeExecutionStatus.FAILED,
        "left": NodeExecutionStatus.FAILED,
        "right": NodeExecutionStatus.FAILED,
        "join": NodeExecutionStatus.FAILED,
        "independent": NodeExecutionStatus.PENDING,
    }
    assert uow.workflow_executions.execution.status is WorkflowExecutionStatus.FAILED


def test_duplicate_failed_completion_does_not_repeat_skip_transitions() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.FAILED)
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
        {
            "root": NodeExecutionStatus.FAILED,
            "child": NodeExecutionStatus.FAILED,
        },
    )
    uow.node_executions.errors["root"] = ("original failure", "RuntimeError")
    uow.node_executions.errors["child"] = ("Dependency 'root' failed.", "FailedDependency")

    decision = asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "root", TaskCompletionStatus.FAILED), uow
        )
    )

    assert decision.outcome is TaskCompletionOutcome.DUPLICATE
    assert uow.node_executions.errors == {
        "root": ("original failure", "RuntimeError"),
        "child": ("Dependency 'root' failed.", "FailedDependency"),
    }


def test_concurrent_failed_completions_propagate_once() -> None:
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
        {
            "root": NodeExecutionStatus.RUNNING,
            "child": NodeExecutionStatus.PENDING,
        },
    )

    async def process_both_failures() -> list[TaskCompletionDecision]:
        return list(
            await asyncio.gather(
                TaskCompletionService().process(
                    _event(execution.execution_id, "root", TaskCompletionStatus.FAILED), uow
                ),
                TaskCompletionService().process(
                    _event(execution.execution_id, "root", TaskCompletionStatus.FAILED), uow
                ),
            )
        )

    decisions = asyncio.run(process_both_failures())

    assert sorted(decision.outcome for decision in decisions) == [
        TaskCompletionOutcome.DUPLICATE,
        TaskCompletionOutcome.PROCESSED,
    ]
    assert uow.node_executions.statuses == {
        "root": NodeExecutionStatus.FAILED,
        "child": NodeExecutionStatus.FAILED,
    }
    assert uow.workflow_executions.execution.status is WorkflowExecutionStatus.FAILED


def test_duplicate_completion_is_a_no_op() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id, [{"id": "node", "handler": "task", "dependencies": []}]
    )
    uow = FakeUnitOfWork(execution, workflow, {"node": NodeExecutionStatus.COMPLETED})
    uow.node_executions.outputs["node"] = {"valid": {"items": [1, 2]}}

    decision = asyncio.run(
        TaskCompletionService().process(
            _event(execution.execution_id, "node", TaskCompletionStatus.COMPLETED), uow
        )
    )

    assert decision.outcome is TaskCompletionOutcome.DUPLICATE
    assert decision.ready_node_ids == ()
    assert uow.node_executions.outputs == {"node": {"valid": {"items": [1, 2]}}}


def test_completion_persistence_failure_does_not_finalize_node_or_workflow() -> None:
    execution = WorkflowExecution(workflow_id=uuid4(), status=WorkflowExecutionStatus.RUNNING)
    workflow = _workflow(
        execution.workflow_id, [{"id": "node", "handler": "task", "dependencies": []}]
    )
    uow = FakeUnitOfWork(execution, workflow, {"node": NodeExecutionStatus.RUNNING})
    uow.node_executions.fail_updates = True

    with pytest.raises(RuntimeError, match="node persistence failed"):
        asyncio.run(
            TaskCompletionService().process(
                _event(execution.execution_id, "node", TaskCompletionStatus.COMPLETED), uow
            )
        )

    assert uow.node_executions.statuses["node"] is NodeExecutionStatus.RUNNING
    assert uow.workflow_executions.execution.status is WorkflowExecutionStatus.RUNNING
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
