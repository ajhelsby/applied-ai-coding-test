from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from json import loads
from typing import cast
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.outbox_event import OutboxEventRecord
from app.messaging import outbox_publisher
from app.messaging.outbox_publisher import OutboxPublisher


class FakeScalarResult:
    def __init__(self, rows: list[OutboxEventRecord]) -> None:
        self._rows = rows

    def all(self) -> list[OutboxEventRecord]:
        return self._rows


class FakeResult:
    def __init__(self, rows: list[OutboxEventRecord]) -> None:
        self._rows = rows

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._rows)


class FakeSession:
    def __init__(self, rows: list[OutboxEventRecord]) -> None:
        self.rows = rows
        self.statement: Select[tuple[OutboxEventRecord]] | None = None
        self.commit_count = 0

    async def execute(self, statement: Select[tuple[OutboxEventRecord]]) -> FakeResult:
        self.statement = statement
        return FakeResult(self.rows)

    async def commit(self) -> None:
        self.commit_count += 1


@asynccontextmanager
async def session_factory(session: FakeSession) -> AsyncIterator[FakeSession]:
    yield session


def make_event() -> OutboxEventRecord:
    execution_id = uuid4()
    return OutboxEventRecord(
        event_id=uuid4(),
        event_type="workflow.execution.triggered",
        aggregate_id=execution_id,
        payload={"execution_id": str(execution_id), "options": {"draft": True}},
        status="pending",
        publish_attempts=0,
    )


def fake_session_factory(session: FakeSession) -> Callable[[], AsyncSession]:
    return cast(Callable[[], AsyncSession], lambda: session_factory(session))


def test_publisher_emits_json_payload_and_marks_event_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = make_event()
    session = FakeSession([event])
    published_fields: list[dict[str, str]] = []

    async def fake_publish(stream: str, fields: dict[str, str]) -> str:
        assert stream == "workflow.events"
        published_fields.append(fields)
        return "1-0"

    monkeypatch.setattr(outbox_publisher, "publish", fake_publish)

    import asyncio

    published = asyncio.run(OutboxPublisher(fake_session_factory(session)).publish_pending())

    assert published == 1
    assert loads(published_fields[0]["payload"]) == event.payload
    assert event.status == "published"
    assert event.published_at is not None
    assert event.publish_attempts == 1
    assert event.last_error is None
    assert session.commit_count == 1


def test_publisher_records_redis_failure_for_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    event = make_event()
    session = FakeSession([event])

    async def fake_publish(stream: str, fields: dict[str, str]) -> str:
        del stream, fields
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(outbox_publisher, "publish", fake_publish)

    import asyncio

    with pytest.raises(ConnectionError, match="Redis unavailable"):
        asyncio.run(OutboxPublisher(fake_session_factory(session)).publish_pending())

    assert event.status == "pending"
    assert event.published_at is None
    assert event.publish_attempts == 1
    assert event.last_error == "Redis unavailable"
    assert session.commit_count == 1


def test_publisher_locks_pending_rows_before_publishing() -> None:
    session = FakeSession([])

    import asyncio

    assert asyncio.run(OutboxPublisher(fake_session_factory(session)).publish_pending()) == 0
    assert session.statement is not None
    assert session.statement._for_update_arg is not None
    assert session.statement._for_update_arg.skip_locked is True
