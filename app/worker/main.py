"""Standalone long-running Redis Streams worker runtime."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Final

from redis.exceptions import RedisError

from app.messaging.redis.client import close_async_redis_client
from app.messaging.redis.streams import (
    WORKFLOW_TASKS_GROUP,
    WORKFLOW_TASKS_STREAM,
    autoclaim,
    consume,
)
from app.messaging.task_messages import NodeTaskMessage
from app.worker.logging import configure_json_logging
from app.worker.task_processor import WorkerTaskProcessor

logger = logging.getLogger(__name__)

TaskProcessor = Callable[[str, str, NodeTaskMessage], Awaitable[None]]
MalformedTaskProcessor = Callable[[str, str, dict[str, str], ValueError], Awaitable[None]]
DEFAULT_MAX_CONCURRENCY: Final[int] = 10
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS: Final[float] = 5.0
DEFAULT_RECLAIM_IDLE_MS: Final[int] = 30_000


class WorkerRuntime:
    """Consume task messages concurrently without acknowledging unfinished work."""

    def __init__(
        self,
        consumer_name: str,
        process_message: TaskProcessor,
        process_malformed_message: MalformedTaskProcessor | None = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        reclaim_idle_ms: int = DEFAULT_RECLAIM_IDLE_MS,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1.")
        if shutdown_timeout_seconds < 0:
            raise ValueError("shutdown_timeout_seconds must not be negative.")
        if reclaim_idle_ms < 0:
            raise ValueError("reclaim_idle_ms must not be negative.")

        self._consumer_name = consumer_name
        self._process_message = process_message
        self._process_malformed_message = process_malformed_message
        self._max_concurrency = max_concurrency
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._reclaim_idle_ms = reclaim_idle_ms
        self._reclaim_start_id = "0-0"
        self._in_flight: set[asyncio.Task[None]] = set()

    async def run(self, stop_event: asyncio.Event) -> None:
        """Consume messages until termination, then cancel remaining work if needed."""

        logger.info(
            "Worker started",
            extra={"consumer": self._consumer_name, "max_concurrency": self._max_concurrency},
        )
        try:
            while not stop_event.is_set():
                await self._wait_for_capacity(stop_event)
                if stop_event.is_set():
                    break

                reclaimed_messages = await self._reclaim_available_messages()
                if reclaimed_messages:
                    self._schedule_messages(reclaimed_messages)
                    continue

                self._schedule_messages(await self._consume_available_messages())
        finally:
            await self._stop_in_flight_work()
            logger.info("Worker stopped", extra={"consumer": self._consumer_name})

    async def _wait_for_capacity(self, stop_event: asyncio.Event) -> None:
        while len(self._in_flight) >= self._max_concurrency and not stop_event.is_set():
            await asyncio.wait(self._in_flight, return_when=asyncio.FIRST_COMPLETED)

    async def _consume_available_messages(
        self,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        try:
            return await consume(
                group=WORKFLOW_TASKS_GROUP,
                consumer=self._consumer_name,
                streams={WORKFLOW_TASKS_STREAM: ">"},
                count=self._max_concurrency - len(self._in_flight),
                block_ms=1000,
            )
        except RedisError:
            logger.exception("Unable to consume worker tasks; will retry")
            return []

    async def _reclaim_available_messages(
        self,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        try:
            self._reclaim_start_id, messages, deleted_message_ids = await autoclaim(
                stream=WORKFLOW_TASKS_STREAM,
                group=WORKFLOW_TASKS_GROUP,
                consumer=self._consumer_name,
                min_idle_ms=self._reclaim_idle_ms,
                start_id=self._reclaim_start_id,
                count=self._max_concurrency - len(self._in_flight),
            )
        except RedisError:
            logger.exception("Unable to reclaim pending worker tasks; will retry")
            return []

        if deleted_message_ids:
            logger.warning(
                "Worker discarded deleted pending task references",
                extra={
                    "consumer": self._consumer_name,
                    "deleted_message_ids": deleted_message_ids,
                },
            )
        if not messages:
            return []

        logger.info(
            "Worker reclaimed pending tasks",
            extra={"consumer": self._consumer_name, "message_count": len(messages)},
        )
        return [(WORKFLOW_TASKS_STREAM, messages)]

    def _schedule_messages(
        self,
        messages: list[tuple[str, list[tuple[str, dict[str, str]]]]],
    ) -> None:
        for stream, stream_messages in messages:
            for message_id, fields in stream_messages:
                task = asyncio.create_task(
                    self._process_one(stream, message_id, fields),
                    name=f"worker-task-{message_id}",
                )
                self._in_flight.add(task)
                task.add_done_callback(self._in_flight.discard)

    async def _process_one(self, stream: str, message_id: str, fields: dict[str, str]) -> None:
        logger.info(
            "Worker received task",
            extra={"consumer": self._consumer_name, "stream": stream, "message_id": message_id},
        )
        try:
            task = NodeTaskMessage.from_stream_fields(fields)
        except ValueError as error:
            logger.exception(
                "Worker received malformed task",
                extra={"consumer": self._consumer_name, "stream": stream, "message_id": message_id},
            )
            if self._process_malformed_message is not None:
                try:
                    await self._process_malformed_message(stream, message_id, fields, error)
                except Exception:
                    logger.exception(
                        "Worker could not publish malformed task failure event",
                        extra={
                            "consumer": self._consumer_name,
                            "stream": stream,
                            "message_id": message_id,
                        },
                    )
            return

        try:
            await self._process_message(stream, message_id, task)
        except Exception:
            logger.exception(
                "Worker task processing failed",
                extra={"consumer": self._consumer_name, "stream": stream, "message_id": message_id},
            )

    async def _stop_in_flight_work(self) -> None:
        if not self._in_flight:
            return

        done, pending = await asyncio.wait(
            self._in_flight,
            timeout=self._shutdown_timeout_seconds,
        )
        del done
        for task in pending:
            task.cancel()
        if pending:
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*pending)


def _consumer_name() -> str:
    configured_name = os.getenv("WORKER_CONSUMER_NAME")
    if configured_name:
        return configured_name
    return f"{socket.gethostname()}-{os.getpid()}"


def _max_concurrency() -> int:
    return int(os.getenv("WORKER_MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY)))


def _shutdown_timeout_seconds() -> float:
    return float(
        os.getenv("WORKER_SHUTDOWN_TIMEOUT_SECONDS", str(DEFAULT_SHUTDOWN_TIMEOUT_SECONDS))
    )


def _reclaim_idle_ms() -> int:
    return int(os.getenv("WORKER_RECLAIM_IDLE_MS", str(DEFAULT_RECLAIM_IDLE_MS)))


def main() -> None:
    stop_event = asyncio.Event()

    def handle_signal(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    configure_json_logging(os.getenv("LOG_LEVEL", "INFO"))
    try:
        task_processor = WorkerTaskProcessor()
        asyncio.run(
            WorkerRuntime(
                consumer_name=_consumer_name(),
                process_message=task_processor.process,
                process_malformed_message=task_processor.process_malformed,
                max_concurrency=_max_concurrency(),
                shutdown_timeout_seconds=_shutdown_timeout_seconds(),
                reclaim_idle_ms=_reclaim_idle_ms(),
            ).run(stop_event)
        )
    finally:
        asyncio.run(close_async_redis_client())


if __name__ == "__main__":
    main()
