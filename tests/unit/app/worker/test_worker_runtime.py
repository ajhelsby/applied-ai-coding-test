from __future__ import annotations

import asyncio

import pytest

from app.messaging.redis.streams import WORKFLOW_TASKS_GROUP, WORKFLOW_TASKS_STREAM
from app.messaging.task_messages import NodeTaskMessage
from app.worker import main


def _task_fields(task_id: str) -> dict[str, str]:
    return {
        "task_id": task_id,
        "execution_id": "76c8dc7e-a3ca-4a31-b951-36501a0d8a1c",
        "node_id": "node-1",
        "handler": "input",
        "handler_config": "{}",
        "resolved_input": "{}",
    }


@pytest.fixture(autouse=True)
def no_pending_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_autoclaim(
        **_kwargs: object,
    ) -> tuple[str, list[tuple[str, dict[str, str]]], list[str]]:
        return "0-0", [], []

    monkeypatch.setattr(main, "autoclaim", fake_autoclaim)


def test_worker_processes_messages_concurrently_and_uses_worker_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = asyncio.Event()
    both_started = asyncio.Event()
    processed: list[str] = []
    consume_calls = 0

    async def fake_consume(**kwargs: object) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        nonlocal consume_calls
        consume_calls += 1
        assert kwargs["group"] == WORKFLOW_TASKS_GROUP
        assert kwargs["streams"] == {WORKFLOW_TASKS_STREAM: ">"}
        if consume_calls == 1:
            return [
                (
                    WORKFLOW_TASKS_STREAM,
                    [("1-0", _task_fields("first")), ("2-0", _task_fields("second"))],
                )
            ]
        await stop_event.wait()
        return []

    async def process_message(_stream: str, message_id: str, task: NodeTaskMessage) -> None:
        processed.append(f"{message_id}:{task.task_id}")
        if len(processed) == 2:
            both_started.set()
        await both_started.wait()
        stop_event.set()

    monkeypatch.setattr(main, "consume", fake_consume)

    asyncio.run(
        main.WorkerRuntime(
            consumer_name="worker-1",
            process_message=process_message,
            max_concurrency=2,
        ).run(stop_event)
    )

    assert processed == ["1-0:first", "2-0:second"]


def test_worker_cancels_in_flight_work_after_shutdown_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = asyncio.Event()
    processing_started = asyncio.Event()
    was_cancelled = False
    consume_calls = 0

    async def fake_consume(**_kwargs: object) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        nonlocal consume_calls
        consume_calls += 1
        if consume_calls == 1:
            return [(WORKFLOW_TASKS_STREAM, [("1-0", _task_fields("first"))])]
        await processing_started.wait()
        stop_event.set()
        return []

    async def process_message(
        _stream: str,
        _message_id: str,
        _task: NodeTaskMessage,
    ) -> None:
        nonlocal was_cancelled
        processing_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            was_cancelled = True
            raise

    monkeypatch.setattr(main, "consume", fake_consume)

    asyncio.run(
        main.WorkerRuntime(
            consumer_name="worker-1",
            process_message=process_message,
            shutdown_timeout_seconds=0,
        ).run(stop_event)
    )

    assert was_cancelled


def test_worker_ignores_malformed_task_without_stopping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = asyncio.Event()
    processed = False
    consume_calls = 0

    async def fake_consume(**_kwargs: object) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        nonlocal consume_calls
        consume_calls += 1
        if consume_calls == 1:
            return [(WORKFLOW_TASKS_STREAM, [("1-0", {"task_id": "missing-fields"})])]
        stop_event.set()
        return []

    async def process_message(
        _stream: str,
        _message_id: str,
        _task: NodeTaskMessage,
    ) -> None:
        nonlocal processed
        processed = True

    monkeypatch.setattr(main, "consume", fake_consume)

    asyncio.run(
        main.WorkerRuntime(
            consumer_name="worker-1",
            process_message=process_message,
        ).run(stop_event)
    )

    assert not processed


def test_worker_reclaims_pending_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = asyncio.Event()
    processed: list[str] = []
    autoclaim_calls = 0

    async def fake_autoclaim(
        **kwargs: object,
    ) -> tuple[str, list[tuple[str, dict[str, str]]], list[str]]:
        nonlocal autoclaim_calls
        autoclaim_calls += 1
        assert kwargs["group"] == WORKFLOW_TASKS_GROUP
        assert kwargs["stream"] == WORKFLOW_TASKS_STREAM
        assert kwargs["min_idle_ms"] == 1_000
        if autoclaim_calls == 1:
            return "1-0", [("1-0", _task_fields("reclaimed"))], []
        return "0-0", [], []

    async def fake_consume(**_kwargs: object) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        await stop_event.wait()
        return []

    async def process_message(_stream: str, message_id: str, _task: NodeTaskMessage) -> None:
        processed.append(message_id)
        stop_event.set()

    monkeypatch.setattr(main, "autoclaim", fake_autoclaim)
    monkeypatch.setattr(main, "consume", fake_consume)

    asyncio.run(
        main.WorkerRuntime(
            consumer_name="worker-1",
            process_message=process_message,
            reclaim_idle_ms=1_000,
        ).run(stop_event)
    )

    assert processed == ["1-0"]
