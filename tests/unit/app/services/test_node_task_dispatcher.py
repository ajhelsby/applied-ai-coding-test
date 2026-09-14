from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from json import loads
from uuid import UUID, uuid4

from redis.exceptions import ConnectionError

from app.domain.models.execution import NodeExecution, WorkflowExecution
from app.domain.models.node import WorkflowNode
from app.domain.state.states import NodeExecutionStatus
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
    ) -> None:
        self.statuses = statuses
        self.outputs = {} if outputs is None else outputs
        self.update_calls: list[tuple[str, NodeExecutionStatus, NodeExecutionStatus]] = []

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        return [
            NodeExecution(
                workflow_execution_id=execution_id,
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


class FakeUnitOfWork:
    def __init__(self, node_executions: FakeNodeExecutions) -> None:
        self.node_executions = node_executions

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
    node_executions = FakeNodeExecutions({node.id: NodeExecutionStatus.READY})
    published: list[dict[str, str]] = []

    async def publish_task(stream: str, fields: dict[str, str]) -> str:
        assert stream == "workflow.tasks"
        published.append(fields)
        return "1-0"

    result = asyncio.run(
        RedisNodeTaskDispatcher(publish_task).dispatch(
            execution,
            node,
            FakeUnitOfWork(node_executions),
        )
    )

    assert result.outcome is DispatchOutcome.DISPATCHED
    assert result.task_id == create_task_id(execution.execution_id, node.id)
    assert published == [
        {
            "task_id": result.task_id,
            "execution_id": str(execution.execution_id),
            "node_id": node.id,
            "handler": "example.handler",
            "handler_config": '{"url":"https://example.com/task"}',
            "resolved_input": '{"url":"https://example.com/task"}',
        }
    ]
    assert node_executions.statuses[node.id] is NodeExecutionStatus.RUNNING


def test_dispatch_many_dispatches_independent_nodes_concurrently() -> None:
    execution = make_execution()
    first_node, second_node = make_node("first"), make_node("second")
    node_executions = FakeNodeExecutions(
        {first_node.id: NodeExecutionStatus.READY, second_node.id: NodeExecutionStatus.READY}
    )
    both_publishes_started = asyncio.Event()
    publish_count = 0

    async def publish_task(_stream: str, _fields: dict[str, str]) -> str:
        nonlocal publish_count
        publish_count += 1
        if publish_count == 2:
            both_publishes_started.set()
        await both_publishes_started.wait()
        return f"{publish_count}-0"

    results = asyncio.run(
        asyncio.wait_for(
            RedisNodeTaskDispatcher(publish_task).dispatch_many(
                execution,
                [first_node, second_node],
                lambda: FakeUnitOfWork(node_executions),
            ),
            timeout=0.1,
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
            node.id: NodeExecutionStatus.READY,
        },
        outputs={"get_posts": {"count": 2}},
    )
    published: list[dict[str, str]] = []

    async def publish_task(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    asyncio.run(
        RedisNodeTaskDispatcher(publish_task).dispatch(
            execution,
            node,
            FakeUnitOfWork(node_executions),
        )
    )

    assert loads(published[0]["resolved_input"]) == {
        "post_count": 2,
        "description": "Found 2 posts.",
    }


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
            node.id: NodeExecutionStatus.READY,
        },
        outputs={
            "get_posts": {"posts": [{"id": 1}]},
            "get_comments": {"comments": [{"post_id": 1}]},
        },
    )
    published: list[dict[str, str]] = []

    async def publish_task(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    asyncio.run(
        RedisNodeTaskDispatcher(publish_task).dispatch(
            execution,
            node,
            FakeUnitOfWork(node_executions),
        )
    )

    assert loads(published[0]["resolved_input"]) == {
        "get_posts": {"posts": [{"id": 1}]},
        "get_comments": {"comments": [{"post_id": 1}]},
    }


def test_duplicate_dispatch_does_not_publish_another_task() -> None:
    execution = make_execution()
    node = make_node()
    node_executions = FakeNodeExecutions({node.id: NodeExecutionStatus.READY})
    published: list[dict[str, str]] = []

    async def publish_task(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    dispatcher = RedisNodeTaskDispatcher(publish_task)
    unit_of_work = FakeUnitOfWork(node_executions)
    first_result = asyncio.run(dispatcher.dispatch(execution, node, unit_of_work))
    duplicate_result = asyncio.run(dispatcher.dispatch(execution, node, unit_of_work))

    assert first_result.outcome is DispatchOutcome.DISPATCHED
    assert duplicate_result.outcome is DispatchOutcome.ALREADY_STARTED
    assert duplicate_result.task_id == first_result.task_id
    assert len(published) == 1


def test_dispatch_releases_claim_when_task_publishing_fails() -> None:
    execution = make_execution()
    node = make_node()
    node_executions = FakeNodeExecutions({node.id: NodeExecutionStatus.READY})

    async def publish_task(_stream: str, _fields: dict[str, str]) -> str:
        raise ConnectionError("Redis unavailable")

    result = asyncio.run(
        RedisNodeTaskDispatcher(publish_task).dispatch(
            execution,
            node,
            FakeUnitOfWork(node_executions),
        )
    )

    assert result.outcome is DispatchOutcome.FAILED_TO_PUBLISH
    assert result.reason == "Redis unavailable"
    assert node_executions.statuses[node.id] is NodeExecutionStatus.READY
    assert node_executions.update_calls == [
        (node.id, NodeExecutionStatus.READY, NodeExecutionStatus.RUNNING),
        (node.id, NodeExecutionStatus.RUNNING, NodeExecutionStatus.READY),
    ]
