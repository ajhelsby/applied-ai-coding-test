"""Redis Stream coordination used by integration-only synchronization hooks."""

from __future__ import annotations

import time

from redis import asyncio as aioredis


class RedisBarrierTimeout(TimeoutError):
    """Raised when an integration barrier is not released in time."""


async def participate_in_barrier(
    client: aioredis.Redis[str],
    name: str,
    participant: str,
    *,
    timeout_seconds: float,
) -> None:
    """Record arrival and wait for the participant-specific release."""

    if timeout_seconds <= 0:
        raise ValueError("Barrier timeout must be greater than zero.")
    arrival_stream = f"integration.barrier:{name}:arrivals"
    release_stream = f"integration.barrier:{name}:releases"
    await client.xadd(arrival_stream, {"participant": participant})

    stream_id = "0-0"
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise RedisBarrierTimeout(
                f"Timed out after {timeout_seconds:.1f}s waiting for release of "
                f"{participant!r} on barrier {name!r}."
            )
        messages = await client.xread(
            streams={release_stream: stream_id},
            count=100,
            block=max(1, int(remaining_seconds * 1000)),
        )
        if not messages:
            raise RedisBarrierTimeout(
                f"Timed out after {timeout_seconds:.1f}s waiting for release of "
                f"{participant!r} on barrier {name!r}."
            )
        for _, stream_messages in messages:
            for message_id, fields in stream_messages:
                stream_id = message_id
                if fields.get("participant") == participant:
                    return
