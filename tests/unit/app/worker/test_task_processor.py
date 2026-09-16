from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.models.json import JsonValue
from app.domain.repositories.task_processing_repository import (
    TaskClaimOutcome,
    TaskProcessingResult,
)
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


class CountingHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, _task: NodeTaskMessage) -> dict[str, object]:
        self.calls += 1
        return {"result": "done"}


class FakeTaskProcessing:
    def __init__(self) -> None:
        self.statuses: dict[str, str] = {}
        self.results: dict[str, TaskProcessingResult] = {}
        self.claim_lock = asyncio.Lock()

    async def claim_task(
        self,
        task_id: str,
        execution_id: UUID,
        node_id: str,
        worker_id: str,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> TaskClaimOutcome:
        del execution_id, node_id, worker_id, claimed_at, claim_expires_at
        async with self.claim_lock:
            status = self.statuses.get(task_id)
            if status == "completed":
                return TaskClaimOutcome.ALREADY_COMPLETED
            if status == "result_recorded":
                return TaskClaimOutcome.RESULT_RECORDED
            if status == "claimed":
                return TaskClaimOutcome.CURRENTLY_CLAIMED
            self.statuses[task_id] = "claimed"
            return TaskClaimOutcome.CLAIMED

    async def record_result(
        self,
        task_id: str,
        event_id: UUID,
        result_data: JsonValue,
        error_message: str | None,
        error_type: str | None,
    ) -> None:
        self.statuses[task_id] = "result_recorded"
        self.results[task_id] = TaskProcessingResult(
            event_id=event_id,
            result_data=result_data,
            error_message=error_message,
            error_type=error_type,
        )

    async def get_result(self, task_id: str) -> TaskProcessingResult:
        return self.results[task_id]

    async def mark_completed(self, task_id: str, completed_at: datetime) -> None:
        del completed_at
        self.statuses[task_id] = "completed"

    async def renew_claim(
        self,
        task_id: str,
        worker_id: str,
        claim_expires_at: datetime,
    ) -> bool:
        del task_id, worker_id, claim_expires_at
        return True


class FakeUnitOfWork:
    def __init__(self, task_processing: FakeTaskProcessing) -> None:
        self.task_processing = task_processing

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeUnitOfWork]:
        yield self


def _idempotent_task() -> NodeTaskMessage:
    return NodeTaskMessage(
        task_id="task-idempotent",
        execution_id=uuid4(),
        node_id="node-1",
        handler="test",
        handler_config={},
        resolved_input={},
    )


def _idempotent_processor(
    task_processing: FakeTaskProcessing,
    handler: CountingHandler,
    published: list[dict[str, str]],
    acknowledged: list[str],
) -> WorkerTaskProcessor:
    async def publish_completion(_stream: str, fields: dict[str, str]) -> str:
        published.append(fields)
        return "completion-1"

    async def acknowledge(_stream: str, _group: str, message_id: str) -> int:
        acknowledged.append(message_id)
        return 1

    return WorkerTaskProcessor(
        executor=WorkerTaskExecutor(NodeHandlerRegistry({"test": handler})),
        completion_publisher=publish_completion,
        acknowledger=acknowledge,
        unit_of_work_factory=lambda: FakeUnitOfWork(task_processing),
        worker_id="worker-1",
    )


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


def test_processor_executes_sequential_duplicate_delivery_once() -> None:
    task_processing = FakeTaskProcessing()
    handler = CountingHandler()
    published: list[dict[str, str]] = []
    acknowledged: list[str] = []
    processor = _idempotent_processor(task_processing, handler, published, acknowledged)
    task = _idempotent_task()

    asyncio.run(processor.process("workflow.tasks", "1-0", task))
    asyncio.run(processor.process("workflow.tasks", "2-0", task))

    assert handler.calls == 1
    assert len(published) == 1
    assert acknowledged == ["1-0", "2-0"]
    assert task_processing.statuses[task.task_id] == "completed"


def test_processor_executes_concurrent_duplicate_delivery_once() -> None:
    task_processing = FakeTaskProcessing()
    handler = CountingHandler()
    published: list[dict[str, str]] = []
    acknowledged: list[str] = []
    first_processor = _idempotent_processor(task_processing, handler, published, acknowledged)
    second_processor = _idempotent_processor(task_processing, handler, published, acknowledged)
    task = _idempotent_task()

    async def process_duplicates() -> None:
        await asyncio.gather(
            first_processor.process("workflow.tasks", "1-0", task),
            second_processor.process("workflow.tasks", "2-0", task),
        )

    asyncio.run(process_duplicates())

    assert handler.calls == 1
    assert len(published) == 1
    assert sorted(acknowledged) == ["1-0", "2-0"]


def test_processor_does_not_execute_completed_task_after_worker_restart() -> None:
    task_processing = FakeTaskProcessing()
    handler = CountingHandler()
    published: list[dict[str, str]] = []
    acknowledged: list[str] = []
    task = _idempotent_task()

    first_processor = _idempotent_processor(task_processing, handler, published, acknowledged)
    second_processor = _idempotent_processor(task_processing, handler, published, acknowledged)

    asyncio.run(first_processor.process("workflow.tasks", "1-0", task))
    asyncio.run(second_processor.process("workflow.tasks", "2-0", task))

    assert handler.calls == 1
    assert len(published) == 1
    assert acknowledged == ["1-0", "2-0"]


def test_processor_replays_persisted_result_after_completion_publish_failure() -> None:
    task_processing = FakeTaskProcessing()
    handler = CountingHandler()
    published: list[dict[str, str]] = []
    acknowledged: list[str] = []
    publish_attempts = 0

    async def publish_completion(_stream: str, fields: dict[str, str]) -> str:
        nonlocal publish_attempts
        publish_attempts += 1
        if publish_attempts == 1:
            raise ConnectionError("Redis unavailable")
        published.append(fields)
        return "completion-1"

    async def acknowledge(_stream: str, _group: str, message_id: str) -> int:
        acknowledged.append(message_id)
        return 1

    processor = WorkerTaskProcessor(
        executor=WorkerTaskExecutor(NodeHandlerRegistry({"test": handler})),
        completion_publisher=publish_completion,
        acknowledger=acknowledge,
        unit_of_work_factory=lambda: FakeUnitOfWork(task_processing),
        worker_id="worker-1",
    )
    task = _idempotent_task()

    try:
        asyncio.run(processor.process("workflow.tasks", "1-0", task))
    except ConnectionError:
        pass
    else:
        raise AssertionError("Expected completion publication to fail.")

    asyncio.run(processor.process("workflow.tasks", "2-0", task))

    assert handler.calls == 1
    assert len(published) == 1
    assert acknowledged == ["2-0"]
    assert task_processing.statuses[task.task_id] == "completed"


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
