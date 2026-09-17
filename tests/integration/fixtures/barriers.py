"""Deterministic Redis coordination primitives for integration tests."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence

from redis import asyncio as aioredis

from app.messaging.redis.barriers import RedisBarrierTimeout


class RedisBarrier:
    """Coordinate independent processes through Redis Streams."""

    def __init__(
        self,
        client: aioredis.Redis[str],
        name: str,
        participants: Sequence[str],
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not name.strip():
            raise ValueError("Barrier name must be non-empty.")
        if not participants:
            raise ValueError("A barrier requires at least one participant.")
        if len(set(participants)) != len(participants):
            raise ValueError("Barrier participants must be unique.")
        if any(not participant.strip() for participant in participants):
            raise ValueError("Barrier participants must be non-empty.")
        if timeout_seconds <= 0:
            raise ValueError("Barrier timeout must be greater than zero.")

        self._client = client
        self._name = name
        self._participants = frozenset(participants)
        self._timeout_seconds = timeout_seconds
        self._arrival_stream = f"integration.barrier:{name}:arrivals"
        self._release_stream = f"integration.barrier:{name}:releases"

    async def arrive(self, participant: str, fields: Mapping[str, str] | None = None) -> str:
        """Record one participant arrival and return its Redis stream ID."""

        self._validate_participant(participant)
        arrival_fields = {"participant": participant}
        if fields is not None:
            arrival_fields.update(fields)
        return str(await self._client.xadd(self._arrival_stream, arrival_fields))

    async def wait_for_arrivals(self) -> frozenset[str]:
        """Wait until every configured participant has arrived."""

        arrived: set[str] = set()
        stream_id = "0-0"
        deadline = time.monotonic() + self._timeout_seconds
        while arrived != self._participants:
            messages = await self._read(
                self._arrival_stream,
                stream_id,
                deadline,
                "arrivals",
            )
            for message_id, fields in messages:
                stream_id = message_id
                participant = fields.get("participant")
                if participant in self._participants:
                    arrived.add(participant)
        return frozenset(arrived)

    async def release(self, participants: Sequence[str] | None = None) -> None:
        """Release selected participants, or all configured participants."""

        selected = self._participants if participants is None else frozenset(participants)
        if not selected:
            raise ValueError("At least one participant must be released.")
        unknown = selected - self._participants
        if unknown:
            raise ValueError(f"Unknown barrier participants: {sorted(unknown)}")
        for participant in selected:
            await self._client.xadd(self._release_stream, {"participant": participant})

    async def wait_for_release(self, participant: str) -> None:
        """Wait until the specified participant receives a release."""

        self._validate_participant(participant)
        stream_id = "0-0"
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            messages = await self._read(
                self._release_stream,
                stream_id,
                deadline,
                f"release for {participant!r}",
            )
            for message_id, fields in messages:
                stream_id = message_id
                if fields.get("participant") == participant:
                    return

    async def cleanup(self) -> None:
        """Delete barrier streams from Redis."""

        await self._client.delete(self._arrival_stream, self._release_stream)

    async def _read(
        self,
        stream: str,
        stream_id: str,
        deadline: float,
        expectation: str,
    ) -> list[tuple[str, dict[str, str]]]:
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise RedisBarrierTimeout(
                f"Timed out after {self._timeout_seconds:.1f}s waiting for {expectation} "
                f"on barrier {self._name!r}."
            )

        messages = await self._client.xread(
            streams={stream: stream_id},
            count=100,
            block=max(1, int(remaining_seconds * 1000)),
        )
        if not messages:
            raise RedisBarrierTimeout(
                f"Timed out after {self._timeout_seconds:.1f}s waiting for {expectation} "
                f"on barrier {self._name!r}."
            )
        return [
            (message_id, fields)
            for _, stream_messages in messages
            for message_id, fields in stream_messages
        ]

    def _validate_participant(self, participant: str) -> None:
        if participant not in self._participants:
            raise ValueError(f"Unknown barrier participant: {participant!r}")
