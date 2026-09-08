from __future__ import annotations

from typing import Final, cast

from redis import asyncio as aioredis

from app.messaging.redis.client import get_async_redis_client

WORKFLOW_TASKS_STREAM: Final[str] = "workflow.tasks"
WORKFLOW_EVENTS_STREAM: Final[str] = "workflow.events"
WORKFLOW_TASK_COMPLETIONS_STREAM: Final[str] = "workflow.task-completions"
WORKFLOW_TASK_DEAD_LETTER_STREAM: Final[str] = "workflow.task-dead-letter"
WORKFLOW_TASKS_GROUP: Final[str] = "workers"
ORCHESTRATOR_COMPLETIONS_GROUP: Final[str] = "orchestrator-completions"


async def publish(
    stream: str,
    fields: dict[str, str],
    client: aioredis.Redis[str] | None = None,
) -> str:
    redis_client = client or get_async_redis_client()
    message_id = await redis_client.xadd(name=stream, fields=fields)
    return str(message_id)


async def consume(
    group: str,
    consumer: str,
    streams: dict[str, str],
    count: int = 1,
    block_ms: int = 5000,
    client: aioredis.Redis[str] | None = None,
) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
    redis_client = client or get_async_redis_client()
    response = await redis_client.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams=streams,
        count=count,
        block=block_ms,
    )
    return list(response)


async def ack(
    stream: str,
    group: str,
    message_id: str,
    client: aioredis.Redis[str] | None = None,
) -> int:
    redis_client = client or get_async_redis_client()
    # redis-py types do not currently type xack; keep a narrow ignore on this call.
    ack_count = await redis_client.xack(stream, group, message_id)  # type: ignore[no-untyped-call]
    return int(cast(int, ack_count))


async def autoclaim(
    stream: str,
    group: str,
    consumer: str,
    min_idle_ms: int,
    start_id: str = "0-0",
    count: int = 100,
    client: aioredis.Redis[str] | None = None,
) -> tuple[str, list[tuple[str, dict[str, str]]], list[str]]:
    redis_client = client or get_async_redis_client()
    next_start_id, claimed_messages, deleted_messages = await redis_client.xautoclaim(
        name=stream,
        groupname=group,
        consumername=consumer,
        min_idle_time=min_idle_ms,
        start_id=start_id,
        count=count,
    )
    return str(next_start_id), list(claimed_messages), list(deleted_messages)
