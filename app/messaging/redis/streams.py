from typing import Final

from redis import asyncio as aioredis  # type: ignore[import-untyped]

from app.messaging.redis.client import get_async_redis_client

WORKFLOW_TASKS_STREAM: Final[str] = "workflow.tasks"
WORKFLOW_EVENTS_STREAM: Final[str] = "workflow.events"


async def publish(
    stream: str,
    fields: dict[str, str],
    client: aioredis.Redis | None = None,
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
    client: aioredis.Redis | None = None,
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
    client: aioredis.Redis | None = None,
) -> int:
    redis_client = client or get_async_redis_client()
    return int(await redis_client.xack(stream, group, message_id))


async def autoclaim(
    stream: str,
    group: str,
    consumer: str,
    min_idle_ms: int,
    start_id: str = "0-0",
    count: int = 100,
    client: aioredis.Redis | None = None,
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
