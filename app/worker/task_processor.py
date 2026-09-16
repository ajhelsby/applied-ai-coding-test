"""Execute worker tasks, publish terminal events, then acknowledge source messages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from json import dumps
from uuid import UUID, uuid4

from app.domain.repositories.task_attempt_processing_repository import (
    TaskAttemptProcessingRepository,
)
from app.domain.repositories.task_processing_repository import (
    TaskClaimOutcome,
    TaskProcessingResult,
)
from app.domain.repositories.unit_of_work import UnitOfWork
from app.messaging.redis.streams import (
    WORKFLOW_TASK_COMPLETIONS_STREAM,
    WORKFLOW_TASK_DEAD_LETTER_STREAM,
    WORKFLOW_TASKS_GROUP,
    ack,
    publish,
)
from app.messaging.stream_fields import is_json_value, required_field
from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers import WorkerTaskExecutor

logger = logging.getLogger(__name__)

CompletionPublisher = Callable[[str, dict[str, str]], Awaitable[str]]
TaskAcknowledger = Callable[[str, str, str], Awaitable[int]]
UnitOfWorkFactory = Callable[[], UnitOfWork]
DEFAULT_TASK_CLAIM_LEASE_SECONDS = 20.0


class WorkerTaskProcessor:
    """Turn validated tasks and malformed task messages into terminal events."""

    def __init__(
        self,
        executor: WorkerTaskExecutor | None = None,
        completion_publisher: CompletionPublisher = publish,
        acknowledger: TaskAcknowledger = ack,
        unit_of_work_factory: UnitOfWorkFactory | None = None,
        worker_id: str = "worker",
        task_claim_lease_seconds: float = DEFAULT_TASK_CLAIM_LEASE_SECONDS,
    ) -> None:
        if task_claim_lease_seconds <= 0:
            raise ValueError("task_claim_lease_seconds must be greater than zero.")
        self._executor = executor or WorkerTaskExecutor()
        self._completion_publisher = completion_publisher
        self._acknowledger = acknowledger
        self._unit_of_work_factory = unit_of_work_factory
        self._worker_id = worker_id
        self._task_claim_lease_seconds = task_claim_lease_seconds

    async def process(self, stream: str, message_id: str, task: NodeTaskMessage) -> None:
        """Execute a task, publish its terminal event, then acknowledge it."""

        if self._unit_of_work_factory is not None:
            claim_outcome = await self._claim_task(task)
            if claim_outcome is not TaskClaimOutcome.CLAIMED:
                if claim_outcome is TaskClaimOutcome.RESULT_RECORDED:
                    event = await self._replay_result(task)
                    await self._publish_complete_and_ack(stream, message_id, event)
                    return
                await self._acknowledger(stream, WORKFLOW_TASKS_GROUP, message_id)
                logger.info(
                    "Worker skipped duplicate task delivery",
                    extra={
                        "task_id": task.task_id,
                        "execution_id": str(task.execution_id),
                        "node_id": task.node_id,
                        "claim_outcome": claim_outcome.value,
                        "message_id": message_id,
                    },
                )
                return

            event = await self._execute_and_record(task)
            await self._publish_complete_and_ack(stream, message_id, event)
            return

        logger.info(
            "Worker executing task",
            extra={
                "task_id": task.task_id,
                "execution_id": str(task.execution_id),
                "node_id": task.node_id,
                "handler": task.handler,
                "message_id": message_id,
            },
        )
        try:
            output = await self._executor.execute(task)
        except Exception as error:
            event = self._failure_event(task, error)
            logger.exception(
                "Worker task execution failed",
                extra={
                    "task_id": task.task_id,
                    "execution_id": str(task.execution_id),
                    "node_id": task.node_id,
                    "message_id": message_id,
                },
            )
        else:
            if not is_json_value(output):
                event = self._failure_event(
                    task,
                    TypeError("Worker task output must contain only JSON-compatible values."),
                )
            else:
                event = TaskCompletionEvent(
                    event_id=uuid4(),
                    task_id=task.task_id,
                    attempt_id=task.attempt_id,
                    attempt_number=task.attempt_number,
                    execution_id=task.execution_id,
                    node_id=task.node_id,
                    status=TaskCompletionStatus.COMPLETED,
                    output_data=output,
                )

        await self._publish_and_ack(stream, message_id, event)

    async def _execute_and_record(self, task: NodeTaskMessage) -> TaskCompletionEvent:
        """Execute a claimed task and persist its result before publication."""

        claim_renewal = asyncio.create_task(
            self._renew_claim_until_complete(task),
            name=f"worker-claim-renewal-{task.attempt_id}",
        )
        try:
            try:
                output = await self._executor.execute(task)
            except Exception as error:
                event = self._failure_event(task, error)
            else:
                if not is_json_value(output):
                    event = self._failure_event(
                        task,
                        TypeError("Worker task output must contain only JSON-compatible values."),
                    )
                else:
                    event = TaskCompletionEvent(
                        event_id=uuid4(),
                        task_id=task.task_id,
                        attempt_id=task.attempt_id,
                        attempt_number=task.attempt_number,
                        execution_id=task.execution_id,
                        node_id=task.node_id,
                        status=TaskCompletionStatus.COMPLETED,
                        output_data=output,
                    )
        finally:
            claim_renewal.cancel()
            with suppress(asyncio.CancelledError):
                await claim_renewal
        await self._record_result(event)
        return event

    async def _renew_claim_until_complete(self, task: NodeTaskMessage) -> None:
        """Keep an active claim valid while its handler is running."""

        interval_seconds = max(self._task_claim_lease_seconds / 3, 0.1)
        while True:
            await asyncio.sleep(interval_seconds)
            expires_at = datetime.now(UTC) + timedelta(seconds=self._task_claim_lease_seconds)
            unit_of_work = self._unit_of_work_factory
            if unit_of_work is None:
                raise RuntimeError("A unit-of-work factory is required to renew worker claims.")
            async with unit_of_work().transaction() as transaction:
                attempt_repository = self._attempt_repository(transaction)
                if attempt_repository is not None:
                    renewed = await attempt_repository.renew_claim(
                        attempt_id=task.attempt_id,
                        worker_id=self._worker_id,
                        claim_expires_at=expires_at,
                    )
                else:
                    renewed = await transaction.task_processing.renew_claim(
                        task_id=task.task_id,
                        worker_id=self._worker_id,
                        claim_expires_at=expires_at,
                    )
            if not renewed:
                raise RuntimeError(
                    f"Worker claim for attempt '{task.attempt_id}' is no longer active."
                )

    async def _record_result(self, event: TaskCompletionEvent) -> None:
        unit_of_work = self._unit_of_work_factory
        if unit_of_work is None:
            raise RuntimeError("A unit-of-work factory is required to record worker results.")
        async with unit_of_work().transaction() as transaction:
            attempt_repository = self._attempt_repository(transaction)
            if attempt_repository is not None:
                await attempt_repository.record_result(
                    attempt_id=event.attempt_id,
                    event_id=event.event_id,
                    result_data=event.output_data,
                    error_message=event.error_message,
                    error_type=event.error_type,
                )
            else:
                await transaction.task_processing.record_result(
                    task_id=event.task_id,
                    event_id=event.event_id,
                    result_data=event.output_data,
                    error_message=event.error_message,
                    error_type=event.error_type,
                )

    async def _replay_result(self, task: NodeTaskMessage) -> TaskCompletionEvent:
        unit_of_work = self._unit_of_work_factory
        if unit_of_work is None:
            raise RuntimeError("A unit-of-work factory is required to replay worker results.")
        async with unit_of_work().transaction() as transaction:
            attempt_repository = self._attempt_repository(transaction)
            if attempt_repository is not None:
                result = await attempt_repository.get_result(task.attempt_id)
            else:
                result = await transaction.task_processing.get_result(task.task_id)
        return self._event_from_result(task, result)

    async def _publish_complete_and_ack(
        self,
        stream: str,
        message_id: str,
        event: TaskCompletionEvent,
    ) -> None:
        await self._completion_publisher(
            WORKFLOW_TASK_COMPLETIONS_STREAM,
            event.to_stream_fields(),
        )
        unit_of_work = self._unit_of_work_factory
        if unit_of_work is None:
            raise RuntimeError("A unit-of-work factory is required to complete worker tasks.")
        async with unit_of_work().transaction() as transaction:
            attempt_repository = self._attempt_repository(transaction)
            if attempt_repository is not None:
                await attempt_repository.mark_completed(
                    attempt_id=event.attempt_id,
                    completed_at=datetime.now(UTC),
                )
            else:
                await transaction.task_processing.mark_completed(
                    task_id=event.task_id,
                    completed_at=datetime.now(UTC),
                )
        await self._acknowledger(stream, WORKFLOW_TASKS_GROUP, message_id)

    @staticmethod
    def _event_from_result(
        task: NodeTaskMessage,
        result: TaskProcessingResult,
    ) -> TaskCompletionEvent:
        if result.error_message is not None or result.error_type is not None:
            if result.error_message is None or result.error_type is None:
                raise ValueError("Persisted failed task results require error information.")
            return TaskCompletionEvent(
                event_id=result.event_id,
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                attempt_number=task.attempt_number,
                execution_id=task.execution_id,
                node_id=task.node_id,
                status=TaskCompletionStatus.FAILED,
                error_message=result.error_message,
                error_type=result.error_type,
            )
        return TaskCompletionEvent(
            event_id=result.event_id,
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            attempt_number=task.attempt_number,
            execution_id=task.execution_id,
            node_id=task.node_id,
            status=TaskCompletionStatus.COMPLETED,
            output_data=result.result_data,
        )

    async def _claim_task(self, task: NodeTaskMessage) -> TaskClaimOutcome:
        """Claim a task in PostgreSQL before invoking its handler."""

        claimed_at = datetime.now(UTC)
        claim_expires_at = claimed_at + timedelta(seconds=self._task_claim_lease_seconds)
        unit_of_work = self._unit_of_work_factory
        if unit_of_work is None:
            raise RuntimeError("A unit-of-work factory is required to claim worker tasks.")
        async with unit_of_work().transaction() as transaction:
            attempt_repository = self._attempt_repository(transaction)
            if attempt_repository is not None:
                return await attempt_repository.claim_attempt(
                    attempt_id=task.attempt_id,
                    task_id=task.task_id,
                    execution_id=task.execution_id,
                    node_id=task.node_id,
                    worker_id=self._worker_id,
                    claimed_at=claimed_at,
                    claim_expires_at=claim_expires_at,
                )
            return await transaction.task_processing.claim_task(
                task_id=task.task_id,
                execution_id=task.execution_id,
                node_id=task.node_id,
                worker_id=self._worker_id,
                claimed_at=claimed_at,
                claim_expires_at=claim_expires_at,
            )

    @staticmethod
    def _attempt_repository(
        transaction: UnitOfWork,
    ) -> TaskAttemptProcessingRepository | None:
        if not hasattr(transaction, "attempt_processing"):
            return None
        return transaction.attempt_processing

    async def process_malformed(
        self,
        stream: str,
        message_id: str,
        fields: Mapping[str, str],
        error: ValueError,
    ) -> None:
        """Publish and acknowledge malformed tasks when their identity is recoverable."""

        try:
            task_id = required_field(fields, "task_id", "Task message")
            attempt_id = UUID(required_field(fields, "attempt_id", "Task message"))
            attempt_number = int(required_field(fields, "attempt_number", "Task message"))
            execution_id = UUID(required_field(fields, "execution_id", "Task message"))
            node_id = required_field(fields, "node_id", "Task message")
        except ValueError as identity_error:
            await self._publish_dead_letter_and_ack(
                stream, message_id, fields, error, identity_error
            )
            return

        event = TaskCompletionEvent(
            event_id=uuid4(),
            task_id=task_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            execution_id=execution_id,
            node_id=node_id,
            status=TaskCompletionStatus.FAILED,
            error_message=str(error),
            error_type=type(error).__name__,
        )
        await self._publish_and_ack(stream, message_id, event)

    async def _publish_and_ack(
        self,
        stream: str,
        message_id: str,
        event: TaskCompletionEvent,
    ) -> None:
        await self._completion_publisher(
            WORKFLOW_TASK_COMPLETIONS_STREAM,
            event.to_stream_fields(),
        )
        await self._acknowledger(stream, WORKFLOW_TASKS_GROUP, message_id)
        logger.info(
            "Worker task completed",
            extra={
                "task_id": event.task_id,
                "execution_id": str(event.execution_id),
                "node_id": event.node_id,
                "status": event.status.value,
                "message_id": message_id,
                "output_data": event.output_data,
                "error_message": event.error_message,
                "error_type": event.error_type,
            },
        )

    async def _publish_dead_letter_and_ack(
        self,
        stream: str,
        message_id: str,
        fields: Mapping[str, str],
        error: ValueError,
        identity_error: ValueError,
    ) -> None:
        await self._completion_publisher(
            WORKFLOW_TASK_DEAD_LETTER_STREAM,
            {
                "source_stream": stream,
                "source_message_id": message_id,
                "raw_fields": dumps(dict(fields), separators=(",", ":"), sort_keys=True),
                "error_message": str(error),
                "error_type": type(error).__name__,
                "identity_error": str(identity_error),
            },
        )
        await self._acknowledger(stream, WORKFLOW_TASKS_GROUP, message_id)
        logger.error(
            "Worker dead-lettered malformed task",
            extra={"stream": stream, "message_id": message_id},
        )

    @staticmethod
    def _failure_event(task: NodeTaskMessage, error: Exception) -> TaskCompletionEvent:
        return TaskCompletionEvent(
            event_id=uuid4(),
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            attempt_number=task.attempt_number,
            execution_id=task.execution_id,
            node_id=task.node_id,
            status=TaskCompletionStatus.FAILED,
            error_message=str(error),
            error_type=type(error).__name__,
        )
