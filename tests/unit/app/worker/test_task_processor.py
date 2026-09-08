from __future__ import annotations

import asyncio
from uuid import uuid4

from app.messaging.redis.streams import (
    WORKFLOW_TASK_COMPLETIONS_STREAM,
    WORKFLOW_TASK_DEAD_LETTER_STREAM,
    WORKFLOW_TASKS_GROUP,
)
from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers import NodeHandlerRegistry, WorkerTaskExecutor
from app.worker.task_processor import WorkerTaskProcessor


class SuccessfulHandler:
    async def execute(self, _task: NodeTaskMessage) -> dict[str, object]:
        return {"result": "done"}


class FailingHandler:
    async def execute(self, _task: NodeTaskMessage) -> dict[str, object]:
        raise RuntimeError("handler failed")


def _task() -> NodeTaskMessage:
    return NodeTaskMessage(
        task_id="task-1",
        execution_id=uuid4(),
        node_id="node-1",
        handler="test",
        handler_config={},
        resolved_input={},
    )


def test_processor_publishes_success_before_acknowledging_task() -> None:
    calls: list[str] = []
    published: list[dict[str, str]] = []

    async def publish_completion(stream: str, fields: dict[str, str]) -> str:
        calls.append("publish")
        assert stream == WORKFLOW_TASK_COMPLETIONS_STREAM
        published.append(fields)
        return "1-0"

    async def acknowledge(stream: str, group: str, message_id: str) -> int:
        calls.append("ack")
        assert (stream, group, message_id) == ("workflow.tasks", WORKFLOW_TASKS_GROUP, "2-0")
        return 1

    processor = WorkerTaskProcessor(
        executor=WorkerTaskExecutor(NodeHandlerRegistry({"test": SuccessfulHandler()})),
        completion_publisher=publish_completion,
        acknowledger=acknowledge,
    )

    asyncio.run(processor.process("workflow.tasks", "2-0", _task()))

    assert calls == ["publish", "ack"]
    assert published[0]["status"] == "completed"
    assert published[0]["output_data"] == '{"result":"done"}'


def test_processor_publishes_failure_when_handler_raises() -> None:
    published: list[dict[str, str]] = []
    acknowledgements: list[str] = []

    async def publish_completion(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    async def acknowledge(_stream: str, _group: str, message_id: str) -> int:
        acknowledgements.append(message_id)
        return 1

    processor = WorkerTaskProcessor(
        executor=WorkerTaskExecutor(NodeHandlerRegistry({"test": FailingHandler()})),
        completion_publisher=publish_completion,
        acknowledger=acknowledge,
    )

    asyncio.run(processor.process("workflow.tasks", "2-0", _task()))

    assert published[0]["status"] == "failed"
    assert published[0]["error_type"] == "RuntimeError"
    assert published[0]["error_message"] == "handler failed"
    assert acknowledgements == ["2-0"]


def test_processor_does_not_acknowledge_when_completion_publish_fails() -> None:
    acknowledged = False

    async def publish_completion(_stream: str, _fields: dict[str, str]) -> str:
        raise ConnectionError("Redis unavailable")

    async def acknowledge(_stream: str, _group: str, _message_id: str) -> int:
        nonlocal acknowledged
        acknowledged = True
        return 1

    processor = WorkerTaskProcessor(
        executor=WorkerTaskExecutor(NodeHandlerRegistry({"test": SuccessfulHandler()})),
        completion_publisher=publish_completion,
        acknowledger=acknowledge,
    )

    try:
        asyncio.run(processor.process("workflow.tasks", "2-0", _task()))
    except ConnectionError:
        pass
    else:
        raise AssertionError("Expected completion publication to fail.")

    assert not acknowledged


def test_processor_reports_and_acknowledges_malformed_task_with_recoverable_identity() -> None:
    published: list[dict[str, str]] = []
    acknowledgements: list[str] = []
    execution_id = uuid4()

    async def publish_completion(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "1-0"

    async def acknowledge(_stream: str, _group: str, message_id: str) -> int:
        acknowledgements.append(message_id)
        return 1

    processor = WorkerTaskProcessor(
        completion_publisher=publish_completion,
        acknowledger=acknowledge,
    )

    asyncio.run(
        processor.process_malformed(
            "workflow.tasks",
            "2-0",
            {
                "task_id": "task-1",
                "execution_id": str(execution_id),
                "node_id": "node-1",
            },
            ValueError("Task message field 'handler' is required."),
        )
    )

    assert published[0]["status"] == "failed"
    assert published[0]["error_type"] == "ValueError"
    assert acknowledgements == ["2-0"]


def test_processor_dead_letters_unidentifiable_malformed_task_before_acknowledging() -> None:
    calls: list[str] = []
    published: list[dict[str, str]] = []

    async def publish_dead_letter(stream: str, fields: dict[str, str]) -> str:
        calls.append("publish")
        assert stream == WORKFLOW_TASK_DEAD_LETTER_STREAM
        published.append(fields)
        return "1-0"

    async def acknowledge(_stream: str, _group: str, _message_id: str) -> int:
        calls.append("ack")
        return 1

    processor = WorkerTaskProcessor(
        completion_publisher=publish_dead_letter,
        acknowledger=acknowledge,
    )

    asyncio.run(
        processor.process_malformed(
            "workflow.tasks",
            "2-0",
            {"resolved_input": "not-json"},
            ValueError("Task message field 'resolved_input' must contain JSON."),
        )
    )

    assert calls == ["publish", "ack"]
    assert published[0]["source_message_id"] == "2-0"
    assert published[0]["raw_fields"] == '{"resolved_input":"not-json"}'
