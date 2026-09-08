from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.domain.repositories.unit_of_work import UnitOfWork
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.messaging.redis.streams import WORKFLOW_TASK_COMPLETIONS_STREAM
from app.messaging.task_completion import TaskCompletionEvent
from app.services.node_task_dispatcher import create_task_id


def test_consumer_processes_and_acknowledges_completion_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.orchestrator import task_completion_consumer
    from app.orchestrator.task_completion_consumer import TaskCompletionConsumer

    execution_id = uuid4()
    fields = {
        "event_id": str(uuid4()),
        "task_id": create_task_id(execution_id, "node"),
        "execution_id": str(execution_id),
        "node_id": "node",
        "status": "completed",
        "output_data": '{"value":"done"}',
    }
    processed_events: list[object] = []
    acknowledgements: list[tuple[str, str, str]] = []

    async def fake_consume(**_kwargs: object) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        return [(WORKFLOW_TASK_COMPLETIONS_STREAM, [("1-0", fields)])]

    async def fake_ack(stream: str, group: str, message_id: str) -> int:
        acknowledgements.append((stream, group, message_id))
        return 1

    class FakeService:
        async def process(self, event: TaskCompletionEvent, _unit_of_work: UnitOfWork) -> None:
            processed_events.append(event)

    monkeypatch.setattr(task_completion_consumer, "consume", fake_consume)
    monkeypatch.setattr(task_completion_consumer, "ack", fake_ack)

    consumer = TaskCompletionConsumer(
        consumer_name="test-consumer",
        unit_of_work_factory=SqlAlchemyUnitOfWork,
        completion_service=FakeService(),
    )

    assert asyncio.run(consumer.consume_once()) == 1
    assert len(processed_events) == 1
    assert acknowledgements == [(WORKFLOW_TASK_COMPLETIONS_STREAM, "orchestrator-completions", "1-0")]
