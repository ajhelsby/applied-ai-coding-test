from __future__ import annotations

from uuid import uuid4

import pytest

from app.messaging.task_completion import TaskCompletionEvent, TaskCompletionStatus
from app.services.node_task_dispatcher import create_task_id


def test_parses_successful_completion_event() -> None:
    execution_id = uuid4()

    event = TaskCompletionEvent.from_stream_fields(
        {
            "event_id": str(uuid4()),
            "task_id": create_task_id(execution_id, "node"),
            "execution_id": str(execution_id),
            "node_id": "node",
            "status": "completed",
            "output_data": '{"answer":42}',
        }
    )

    assert event.status is TaskCompletionStatus.COMPLETED
    assert event.output_data == {"answer": 42}


def test_rejects_success_event_without_object_output() -> None:
    execution_id = uuid4()

    with pytest.raises(ValueError, match="JSON object"):
        TaskCompletionEvent.from_stream_fields(
            {
                "event_id": str(uuid4()),
                "task_id": create_task_id(execution_id, "node"),
                "execution_id": str(execution_id),
                "node_id": "node",
                "status": "completed",
                "output_data": "[]",
            }
        )


def test_parses_failed_completion_event() -> None:
    execution_id = uuid4()

    event = TaskCompletionEvent.from_stream_fields(
        {
            "event_id": str(uuid4()),
            "task_id": create_task_id(execution_id, "node"),
            "execution_id": str(execution_id),
            "node_id": "node",
            "status": "failed",
            "error_message": "request timed out",
            "error_type": "TimeoutError",
        }
    )

    assert event.status is TaskCompletionStatus.FAILED
    assert event.error_message == "request timed out"
    assert event.error_type == "TimeoutError"
