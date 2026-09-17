from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.models.node import WorkflowNode
from app.domain.state.states import NodeExecutionStatus
from app.domain.templates.parser import TemplateResolutionError
from app.services.node_task_dispatcher import (
    DispatchOutcome,
    RedisNodeTaskDispatcher,
    create_task_id,
)


class FakeNodeExecutions:
    def __init__(
        self,
        statuses: dict[str, NodeExecutionStatus],
        outputs: dict[str, dict[str, object]] | None = None,
        execution_ids: dict[str, UUID] | None = None,
    ) -> None:
        self.statuses = statuses
        self.outputs = {} if outputs is None else outputs
        self.execution_ids = {} if execution_ids is None else execution_ids
        self.update_calls: list[tuple[str, NodeExecutionStatus, NodeExecutionStatus]] = []

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        return [
            NodeExecution(
                workflow_execution_id=self.execution_ids.get(node_id, execution_id),
                node_id=node_id,
                status=status,
                output_data=self.outputs.get(node_id, {}),
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
        if self.statuses[node_id] != expected_current_status:
            return False
        self.statuses[node_id] = new_status
        return True

    async def claim_pending_nodes(
        self,
        execution_id: UUID,
        node_ids: Sequence[str],
    ) -> tuple[str, ...]:
        del execution_id
        claimed_ids = tuple(
            node_id
            for node_id in node_ids
            if self.statuses.get(node_id) is NodeExecutionStatus.PENDING
        )
        for node_id in claimed_ids:
            self.statuses[node_id] = NodeExecutionStatus.RUNNING
        return claimed_ids

    async def fail_pending_nodes(
        self,
        _execution_id: UUID,
        node_ids: Sequence[str],
        *,
        reason: str,
        completed_at: object,
    ) -> tuple[str, ...]:
        del reason, completed_at
        skipped_ids = tuple(
            node_id
            for node_id in node_ids
            if self.statuses.get(node_id) is NodeExecutionStatus.PENDING
        )
        for node_id in skipped_ids:
            self.statuses[node_id] = NodeExecutionStatus.FAILED
        return skipped_ids


class FakeWorkflowExecutions:
    async def get_execution_by_id_for_update(self, _execution_id: UUID) -> WorkflowExecution:
        return WorkflowExecution(workflow_id=uuid4())


class FakeOutboxEvents:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.message_ids: list[UUID] = []
        self.payloads: list[dict[str, object]] = []

    async def add_task(
        self,
        *,
        message_id: UUID,
        payload: dict[str, object],
        aggregate_id: UUID | None = None,
    ) -> None:
        del aggregate_id
        self.messages.append(payload)
        self.message_ids.append(message_id)
        self.payloads.append(payload)


class FakeUnitOfWork:
    def __init__(self, node_executions: FakeNodeExecutions) -> None:
        self.node_executions = node_executions
        self.workflow_executions = FakeWorkflowExecutions()
        self.outbox_events = FakeOutboxEvents()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeUnitOfWork]:
        yield self


def make_execution() -> WorkflowExecution:
    return WorkflowExecution(workflow_id=uuid4())


def make_node(node_id: str = "node-1") -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        handler="example.handler",
        config={"url": "https://example.com/task"},
    )


def test_dispatch_publishes_task_after_claiming_node() -> None:
    execution = make_execution()
    node = make_node()
    node_executions = FakeNodeExecutions({node.id: NodeExecutionStatus.PENDING})
    unit_of_work = FakeUnitOfWork(node_executions)

    result = asyncio.run(
        RedisNodeTaskDispatcher().dispatch(
            execution,
            node,
            unit_of_work,
        )
    )

    assert result.outcome is DispatchOutcome.DISPATCHED
    assert result.task_id == create_task_id(execution.execution_id, node.id)
    assert unit_of_work.outbox_events.message_ids == [UUID(result.task_id)]
    assert unit_of_work.outbox_events.payloads == [
        {
            "task_id": result.task_id,
            "attempt_id": unit_of_work.outbox_events.payloads[0]["attempt_id"],
            "attempt_number": 1,
            "execution_id": str(execution.execution_id),
            "node_id": node.id,
            "handler": "example.handler",
            "handler_config": {"url": "https://example.com/task"},
            "resolved_input": {"url": "https://example.com/task"},
        }
    ]
    assert node_executions.statuses[node.id] is NodeExecutionStatus.RUNNING


def test_dispatch_fails_pending_node_when_dependency_failed() -> None:
    execution = make_execution()
    node = make_node("downstream")
    node = node.model_copy(update={"dependencies": ["failed"]})
    node_executions = FakeNodeExecutions(
        {
            "failed": NodeExecutionStatus.FAILED,
            node.id: NodeExecutionStatus.PENDING,
        }
    )
    published: list[dict[str, str]] = []

    async def publish_task(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    result = asyncio.run(
        RedisNodeTaskDispatcher(publish_task).dispatch(
            execution,
            node,
            FakeUnitOfWork(node_executions),
        )
    )

    assert result.outcome is DispatchOutcome.ALREADY_STARTED
    assert result.reason == "A required dependency failed; node was marked failed."
    assert node_executions.statuses[node.id] is NodeExecutionStatus.FAILED
    assert published == []


def test_dispatch_many_dispatches_independent_nodes_concurrently() -> None:
    execution = make_execution()
    first_node, second_node = make_node("first"), make_node("second")
    node_executions = FakeNodeExecutions(
        {first_node.id: NodeExecutionStatus.PENDING, second_node.id: NodeExecutionStatus.PENDING}
    )
    results = asyncio.run(
        RedisNodeTaskDispatcher().dispatch_many(
            execution,
            [first_node, second_node],
            lambda: FakeUnitOfWork(node_executions),
        )
    )

    assert [result.outcome for result in results] == [
        DispatchOutcome.DISPATCHED,
        DispatchOutcome.DISPATCHED,
    ]


def test_dispatch_resolves_templates_from_completed_dependency_outputs() -> None:
    execution = make_execution()
    node = WorkflowNode(
        id="summarize",
        handler="example.handler",
        dependencies=["get_posts"],
        config={
            "post_count": "{{ get_posts.count }}",
            "description": "Found {{ get_posts.count }} posts.",
        },
    )
    node_executions = FakeNodeExecutions(
        {
            "get_posts": NodeExecutionStatus.COMPLETED,
            node.id: NodeExecutionStatus.PENDING,
        },
        outputs={"get_posts": {"count": 2}},
    )
    unit_of_work = FakeUnitOfWork(node_executions)

    asyncio.run(
        RedisNodeTaskDispatcher().dispatch(
            execution,
            node,
            unit_of_work,
        )
    )

    assert unit_of_work.outbox_events.payloads[0]["resolved_input"] == {
        "post_count": 2,
        "description": "Found 2 posts.",
    }


@pytest.mark.parametrize(
    "dependency_status",
    [NodeExecutionStatus.PENDING, NodeExecutionStatus.FAILED],
)
def test_dispatch_does_not_resolve_incomplete_dependency_outputs(
    dependency_status: NodeExecutionStatus,
) -> None:
    execution = make_execution()
    node = WorkflowNode(
        id="summarize",
        handler="example.handler",
        dependencies=["get_user"],
        config={"user_id": "{{ get_user.id }}"},
    )
    node_executions = FakeNodeExecutions(
        {
            "get_user": dependency_status,
            node.id: NodeExecutionStatus.PENDING,
        },
        outputs={"get_user": {"id": 123}},
    )
    published: list[dict[str, str]] = []

    async def publish_task(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    if dependency_status is NodeExecutionStatus.FAILED:
        result = asyncio.run(
            RedisNodeTaskDispatcher(publish_task).dispatch(
                execution,
                node,
                FakeUnitOfWork(node_executions),
            )
        )
        assert result.outcome is DispatchOutcome.ALREADY_STARTED
        assert result.reason == "A required dependency failed; node was marked failed."
        assert node_executions.statuses[node.id] is NodeExecutionStatus.FAILED
    else:
        with pytest.raises(TemplateResolutionError, match="unavailable dependency output"):
            asyncio.run(
                RedisNodeTaskDispatcher(publish_task).dispatch(
                    execution,
                    node,
                    FakeUnitOfWork(node_executions),
                )
            )
        assert node_executions.statuses[node.id] is NodeExecutionStatus.PENDING

    assert published == []
    assert node_executions.update_calls == []


def test_dispatch_does_not_resolve_outputs_from_another_execution() -> None:
    execution = make_execution()
    node = WorkflowNode(
        id="summarize",
        handler="example.handler",
        dependencies=["get_user"],
        config={"user_id": "{{ get_user.id }}"},
    )
    node_executions = FakeNodeExecutions(
        {
            "get_user": NodeExecutionStatus.COMPLETED,
            node.id: NodeExecutionStatus.PENDING,
        },
        outputs={"get_user": {"id": 123}},
        execution_ids={"get_user": uuid4()},
    )
    published: list[dict[str, str]] = []

    async def publish_task(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    with pytest.raises(TemplateResolutionError, match="unavailable dependency output"):
        asyncio.run(
            RedisNodeTaskDispatcher(publish_task).dispatch(
                execution,
                node,
                FakeUnitOfWork(node_executions),
            )
        )

    assert published == []
    assert node_executions.statuses[node.id] is NodeExecutionStatus.PENDING


def test_dispatch_does_not_publish_when_output_path_is_missing() -> None:
    execution = make_execution()
    node = WorkflowNode(
        id="summarize",
        handler="example.handler",
        dependencies=["get_user"],
        config={"user_name": "{{ get_user.profile.name }}"},
    )
    node_executions = FakeNodeExecutions(
        {
            "get_user": NodeExecutionStatus.COMPLETED,
            node.id: NodeExecutionStatus.PENDING,
        },
        outputs={"get_user": {"profile": {}}},
    )
    published: list[dict[str, str]] = []

    async def publish_task(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    with pytest.raises(TemplateResolutionError, match="missing output"):
        asyncio.run(
            RedisNodeTaskDispatcher(publish_task).dispatch(
                execution,
                node,
                FakeUnitOfWork(node_executions),
            )
        )

    assert published == []
    assert node_executions.statuses[node.id] is NodeExecutionStatus.PENDING


def test_dispatch_aggregates_completed_fan_in_dependencies_for_output_node() -> None:
    execution = make_execution()
    node = WorkflowNode(
        id="output",
        handler="output",
        dependencies=["get_posts", "get_comments"],
    )
    node_executions = FakeNodeExecutions(
        {
            "get_posts": NodeExecutionStatus.COMPLETED,
            "get_comments": NodeExecutionStatus.COMPLETED,
            node.id: NodeExecutionStatus.PENDING,
        },
        outputs={
            "get_posts": {"posts": [{"id": 1}]},
            "get_comments": {"comments": [{"post_id": 1}]},
        },
    )
    unit_of_work = FakeUnitOfWork(node_executions)

    asyncio.run(
        RedisNodeTaskDispatcher().dispatch(
            execution,
            node,
            unit_of_work,
        )
    )

    assert unit_of_work.outbox_events.payloads[0]["resolved_input"] == {
        "get_posts": {"posts": [{"id": 1}]},
        "get_comments": {"comments": [{"post_id": 1}]},
    }


def test_duplicate_dispatch_does_not_publish_another_task() -> None:
    execution = make_execution()
    node = make_node()
    node_executions = FakeNodeExecutions({node.id: NodeExecutionStatus.PENDING})
    unit_of_work = FakeUnitOfWork(node_executions)
    dispatcher = RedisNodeTaskDispatcher()
    first_result = asyncio.run(dispatcher.dispatch(execution, node, unit_of_work))
    duplicate_result = asyncio.run(dispatcher.dispatch(execution, node, unit_of_work))

    assert first_result.outcome is DispatchOutcome.DISPATCHED
    assert duplicate_result.outcome is DispatchOutcome.ALREADY_STARTED
    assert duplicate_result.task_id == first_result.task_id
    assert len(unit_of_work.outbox_events.messages) == 1


def test_dispatch_records_task_when_redis_is_unavailable() -> None:
    execution = make_execution()
    node = make_node()
    node_executions = FakeNodeExecutions({node.id: NodeExecutionStatus.PENDING})

    result = asyncio.run(
        RedisNodeTaskDispatcher().dispatch(
            execution,
            node,
            FakeUnitOfWork(node_executions),
        )
    )

    assert result.outcome is DispatchOutcome.DISPATCHED
    assert node_executions.statuses[node.id] is NodeExecutionStatus.RUNNING
    assert node_executions.update_calls == []
