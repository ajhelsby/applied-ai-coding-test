"""PostgreSQL and Redis inspection helpers for asynchronous integration failures."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg2
import redis

from tests.integration.fixtures.infrastructure import InfrastructureConfig


@dataclass(frozen=True, slots=True)
class DatabaseDiagnostics:
    """Persisted state relevant to one workflow execution."""

    workflow_execution: tuple[object, ...] | None
    node_executions: tuple[tuple[object, ...], ...]
    logical_tasks: tuple[tuple[object, ...], ...]
    task_attempts: tuple[tuple[object, ...], ...]
    task_processing: tuple[tuple[object, ...], ...]
    outbox_events: tuple[tuple[object, ...], ...]


def inspect_database(
    infrastructure: InfrastructureConfig,
    execution_id: UUID,
) -> DatabaseDiagnostics:
    """Read workflow, task, attempt, and outbox state from PostgreSQL."""

    connection = psycopg2.connect(infrastructure.database_url.replace("+asyncpg", ""))
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT execution_id, status, started_at, completed_at
                FROM workflow_executions
                WHERE execution_id = %s
                """,
                (execution_id,),
            )
            workflow_execution = cursor.fetchone()

            cursor.execute(
                """
                SELECT node_id, status, started_at, completed_at
                FROM node_executions
                WHERE workflow_execution_id = %s
                ORDER BY node_id
                """,
                (execution_id,),
            )
            node_executions = cursor.fetchall()

            cursor.execute(
                """
                SELECT task_id, node_id, status, created_at, updated_at
                FROM logical_tasks
                WHERE execution_id = %s
                ORDER BY node_id, task_id
                """,
                (execution_id,),
            )
            logical_tasks = cursor.fetchall()

            cursor.execute(
                """
                SELECT attempt_id, task_id, attempt_number, status,
                       claimed_by, completion_event_id, completed_at
                FROM task_attempts
                WHERE task_id IN (
                    SELECT task_id FROM logical_tasks WHERE execution_id = %s
                )
                ORDER BY task_id, attempt_number
                """,
                (execution_id,),
            )
            task_attempts = cursor.fetchall()

            cursor.execute(
                """
                SELECT task_id, node_id, status, claimed_by, completion_event_id, completed_at
                FROM task_processing
                WHERE execution_id = %s
                ORDER BY node_id, task_id
                """,
                (execution_id,),
            )
            task_processing = cursor.fetchall()

            cursor.execute(
                """
                SELECT message_id, message_type, target_stream, status, payload
                FROM outbox_events
                WHERE aggregate_id = %s
                   OR payload->>'execution_id' = %s
                ORDER BY message_id
                """,
                (execution_id, str(execution_id)),
            )
            outbox_events = cursor.fetchall()
    finally:
        connection.close()

    return DatabaseDiagnostics(
        workflow_execution=workflow_execution,
        node_executions=tuple(node_executions),
        logical_tasks=tuple(logical_tasks),
        task_attempts=tuple(task_attempts),
        task_processing=tuple(task_processing),
        outbox_events=tuple(outbox_events),
    )


def inspect_redis_streams(
    infrastructure: InfrastructureConfig,
    streams: tuple[str, ...],
) -> dict[str, tuple[tuple[str, dict[str, str]], ...]]:
    """Read all currently retained entries from selected Redis Streams."""

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        snapshots: dict[str, tuple[tuple[str, dict[str, str]], ...]] = {}
        for stream in streams:
            snapshots[stream] = tuple(
                (message_id, fields) for message_id, fields in client.xrange(stream)
            )
        return snapshots
    finally:
        client.close()


def format_diagnostics(
    database: DatabaseDiagnostics,
    streams: dict[str, tuple[tuple[str, dict[str, str]], ...]],
) -> str:
    """Format persisted and transport state for assertion and timeout messages."""

    stream_lines = [f"{stream}={entries!r}" for stream, entries in sorted(streams.items())]
    return (
        f"workflow_execution={database.workflow_execution!r}\n"
        f"node_executions={database.node_executions!r}\n"
        f"logical_tasks={database.logical_tasks!r}\n"
        f"task_attempts={database.task_attempts!r}\n"
        f"task_processing={database.task_processing!r}\n"
        f"outbox_events={database.outbox_events!r}\n"
        f"redis_streams={'; '.join(stream_lines)}"
    )
