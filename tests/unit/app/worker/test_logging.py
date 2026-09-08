from __future__ import annotations

import json
import logging

from app.worker.logging import JsonFormatter


def test_json_formatter_includes_log_context() -> None:
    record = logging.makeLogRecord(
        {
            "name": "app.worker",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "Worker completed task",
            "args": (),
            "task_id": "task-1",
            "execution_id": "execution-1",
        }
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.worker"
    assert payload["message"] == "Worker completed task"
    assert payload["task_id"] == "task-1"
    assert payload["execution_id"] == "execution-1"
