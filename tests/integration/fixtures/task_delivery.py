"""Real Redis task-delivery and persistence inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg2
import redis

from app.messaging.redis.streams import (
    WORKFLOW_TASK_COMPLETIONS_STREAM,
    WORKFLOW_TASKS_STREAM,
)
from app.messaging.task_messages import NodeTaskMessage
from tests.integration.fixtures.infrastructure import InfrastructureConfig


@dataclass(frozen=True, slots=True)
class TaskPersistenceSnapshot:
    """Persisted state for one logical task and its attempt."""

    logical_task: tuple[object, ...] | None
    attempt: tuple[object, ...] | None
    task_processing: tuple[object, ...] | None
    node_execution: tuple[object, ...] | None


def publish_task_deliveries(
    infrastructure: InfrastructureConfig,
    task: NodeTaskMessage,
    *,
    count: int = 1,
) -> tuple[str, ...]:
    """Publish one or more physical Redis messages for the same logical task."""

    if count < 1:
        raise ValueError("count must be at least one.")

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        fields = task.to_stream_fields()
        return tuple(str(client.xadd(WORKFLOW_TASKS_STREAM, fields)) for _ in range(count))
    finally:
        client.close()


def read_task_stream(
    infrastructure: InfrastructureConfig,
) -> tuple[tuple[str, dict[str, str]], ...]:
    """Read retained task messages with their physical Redis stream IDs."""

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        return tuple(
            (message_id, fields) for message_id, fields in client.xrange(WORKFLOW_TASKS_STREAM)
        )
    finally:
        client.close()


def read_completion_stream(
    infrastructure: InfrastructureConfig,
) -> tuple[tuple[str, dict[str, str]], ...]:
    """Read retained completion messages with their physical Redis stream IDs."""

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        return tuple(
            (message_id, fields)
            for message_id, fields in client.xrange(WORKFLOW_TASK_COMPLETIONS_STREAM)
        )
    finally:
        client.close()


def read_execution_counter(
    infrastructure: InfrastructureConfig,
    counter_name: str,
) -> int:
    """Read the Redis-backed count of actual integration-handler invocations."""

    if not counter_name.strip():
        raise ValueError("counter_name must be non-empty.")

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        value = client.get(f"integration.handler-executions:{counter_name}")
        return 0 if value is None else int(value)
    finally:
        client.close()


def inspect_task_persistence(
    infrastructure: InfrastructureConfig,
    task_id: str,
    attempt_id: UUID,
) -> TaskPersistenceSnapshot:
    """Read logical-task, attempt, processing, and node state from PostgreSQL."""

    database_url = infrastructure.database_url.replace("+asyncpg", "")
    connection = psycopg2.connect(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT task_id, execution_id, node_id, status
                FROM logical_tasks
                WHERE task_id = %s
                """,
                (task_id,),
            )
            logical_task = cursor.fetchone()

            cursor.execute(
                """
                SELECT attempt_id, task_id, attempt_number, status,
                       claimed_by, completion_event_id, result_data, completed_at
                FROM task_attempts
                WHERE attempt_id = %s
                """,
                (attempt_id,),
            )
            attempt = cursor.fetchone()

            cursor.execute(
                """
                SELECT task_id, execution_id, node_id, status,
                       claimed_by, completion_event_id, result_data, completed_at
                FROM task_processing
                WHERE task_id = %s
                """,
                (task_id,),
            )
            task_processing = cursor.fetchone()

            node_execution = None
            if logical_task is not None:
                cursor.execute(
                    """
                    SELECT workflow_execution_id, node_id, status, output_data,
                           started_at, completed_at
                    FROM node_executions
                    WHERE workflow_execution_id = %s
                      AND node_id = %s
                    """,
                    (logical_task[1], logical_task[2]),
                )
                node_execution = cursor.fetchone()
    finally:
        connection.close()

    return TaskPersistenceSnapshot(
        logical_task=logical_task,
        attempt=attempt,
        task_processing=task_processing,
        node_execution=node_execution,
    )
