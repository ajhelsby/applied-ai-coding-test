from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.messaging.task_messages import NodeTaskMessage


def test_parses_and_serializes_self_contained_task_message() -> None:
    execution_id = uuid4()
    fields = {
        "task_id": "task-1",
        "execution_id": str(execution_id),
        "node_id": "node-1",
        "handler": "call_external_service",
        "handler_config": '{"url":"https://example.com"}',
        "resolved_input": '{"query":"hello"}',
    }

    task = NodeTaskMessage.from_stream_fields(fields)

    assert task.execution_id == execution_id
    assert task.handler == "call_external_service"
    assert task.handler_config == {"url": "https://example.com"}
    assert task.resolved_input == {"query": "hello"}
    assert task.to_stream_fields() == fields


def test_rejects_task_with_invalid_handler_config() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        NodeTaskMessage.from_stream_fields(
            {
                "task_id": "task-1",
                "execution_id": str(uuid4()),
                "node_id": "node-1",
                "handler": "input",
                "handler_config": "[]",
                "resolved_input": "{}",
            }
        )


def test_rejects_task_with_invalid_execution_identifier() -> None:
    with pytest.raises(ValidationError):
        NodeTaskMessage.from_stream_fields(
            {
                "task_id": "task-1",
                "execution_id": "not-a-uuid",
                "node_id": "node-1",
                "handler": "input",
                "handler_config": "{}",
                "resolved_input": "{}",
            }
        )
