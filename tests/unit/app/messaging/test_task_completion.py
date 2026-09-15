from __future__ import annotations

from uuid import uuid4

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


def test_parses_successful_completion_event_with_structured_array_output() -> None:
    execution_id = uuid4()

    event = TaskCompletionEvent.from_stream_fields(
        {
            "event_id": str(uuid4()),
            "task_id": create_task_id(execution_id, "node"),
            "execution_id": str(execution_id),
            "node_id": "node",
            "status": "completed",
            "output_data": '[{"items":[1,2,3]}]',
        }
    )

    assert event.output_data == [{"items": [1, 2, 3]}]


def test_parses_successful_completion_event_with_null_output() -> None:
    execution_id = uuid4()

    event = TaskCompletionEvent.from_stream_fields(
        {
            "event_id": str(uuid4()),
            "task_id": create_task_id(execution_id, "node"),
            "execution_id": str(execution_id),
            "node_id": "node",
            "status": "completed",
            "output_data": "null",
        }
    )

    assert event.output_data is None


def test_serializes_structured_and_null_success_output() -> None:
    execution_id = uuid4()

    structured_event = TaskCompletionEvent(
        event_id=uuid4(),
        task_id=create_task_id(execution_id, "node"),
        execution_id=execution_id,
        node_id="node",
        status=TaskCompletionStatus.COMPLETED,
        output_data={"items": [{"value": 1}, {"value": 2}]},
    )
    null_event = TaskCompletionEvent(
        event_id=uuid4(),
        task_id=create_task_id(execution_id, "node"),
        execution_id=execution_id,
        node_id="node",
        status=TaskCompletionStatus.COMPLETED,
        output_data=None,
    )

    assert structured_event.to_stream_fields()["output_data"] == (
        '{"items":[{"value":1},{"value":2}]}'
    )
    assert null_event.to_stream_fields()["output_data"] == "null"


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
