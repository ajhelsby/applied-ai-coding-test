"""Execute worker tasks, publish terminal events, then acknowledge source messages."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from json import dumps
from uuid import UUID, uuid4

from app.messaging.redis.streams import (
    WORKFLOW_TASK_COMPLETIONS_STREAM,
    WORKFLOW_TASK_DEAD_LETTER_STREAM,
    WORKFLOW_TASKS_GROUP,
    ack,
    publish,
)
from app.messaging.stream_fields import required_field
from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers import WorkerTaskExecutor

logger = logging.getLogger(__name__)

CompletionPublisher = Callable[[str, dict[str, str]], Awaitable[str]]
TaskAcknowledger = Callable[[str, str, str], Awaitable[int]]


class WorkerTaskProcessor:
    """Turn validated tasks and malformed task messages into terminal events."""

    def __init__(
        self,
        executor: WorkerTaskExecutor | None = None,
        completion_publisher: CompletionPublisher = publish,
        acknowledger: TaskAcknowledger = ack,
    ) -> None:
        self._executor = executor or WorkerTaskExecutor()
        self._completion_publisher = completion_publisher
        self._acknowledger = acknowledger

    async def process(self, stream: str, message_id: str, task: NodeTaskMessage) -> None:
        """Execute a task, publish its terminal event, then acknowledge it."""

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
            event = TaskCompletionEvent(
                event_id=uuid4(),
                task_id=task.task_id,
                execution_id=task.execution_id,
                node_id=task.node_id,
                status=TaskCompletionStatus.COMPLETED,
                output_data=output,
            )

        await self._publish_and_ack(stream, message_id, event)

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
            execution_id=task.execution_id,
            node_id=task.node_id,
            status=TaskCompletionStatus.FAILED,
            error_message=str(error),
            error_type=type(error).__name__,
        )
