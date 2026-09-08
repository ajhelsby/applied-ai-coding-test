from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers import (
    NodeHandlerRegistry,
    UnknownNodeHandlerError,
    WorkerTaskExecutor,
)


def _task(handler: str, handler_config: dict[str, object] | None = None) -> NodeTaskMessage:
    return NodeTaskMessage(
        task_id="task-1",
        execution_id=uuid4(),
        node_id="node-1",
        handler=handler,
        handler_config=handler_config or {},
        resolved_input={"value": "resolved"},
    )


def test_input_handler_returns_resolved_input() -> None:
    output = asyncio.run(WorkerTaskExecutor().execute(_task("input")))

    assert output == {"value": "resolved"}


def test_external_service_handler_returns_mocked_response() -> None:
    output = asyncio.run(
        WorkerTaskExecutor().execute(
            _task("call_external_service", {"url": "https://example.com/service"})
        )
    )

    assert output == {
        "status": "mocked",
        "url": "https://example.com/service",
        "input": {"value": "resolved"},
    }


def test_unknown_handler_is_rejected() -> None:
    with pytest.raises(UnknownNodeHandlerError, match="unknown"):
        NodeHandlerRegistry().resolve("unknown")
