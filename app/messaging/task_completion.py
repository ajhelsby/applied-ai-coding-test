"""Worker task completion event contract and stream-message parsing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError, loads
from uuid import UUID


class TaskCompletionStatus(StrEnum):
    """Terminal outcomes reported by workers."""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TaskCompletionEvent:
    """A worker-reported terminal outcome for one dispatched task."""

    event_id: UUID
    task_id: str
    execution_id: UUID
    node_id: str
    status: TaskCompletionStatus
    output_data: dict[str, object] | None = None
    error_message: str | None = None
    error_type: str | None = None

    @classmethod
    def from_stream_fields(cls, fields: Mapping[str, str]) -> TaskCompletionEvent:
        """Parse and validate a flat Redis stream completion event."""

        event_id = UUID(_required_field(fields, "event_id"))
        task_id = _required_field(fields, "task_id")
        execution_id = UUID(_required_field(fields, "execution_id"))
        node_id = _required_field(fields, "node_id")
        status = TaskCompletionStatus(_required_field(fields, "status"))

        if status is TaskCompletionStatus.COMPLETED:
            output_data = _parse_output_data(_required_field(fields, "output_data"))
            return cls(
                event_id=event_id,
                task_id=task_id,
                execution_id=execution_id,
                node_id=node_id,
                status=status,
                output_data=output_data,
            )

        return cls(
            event_id=event_id,
            task_id=task_id,
            execution_id=execution_id,
            node_id=node_id,
            status=status,
            error_message=_required_field(fields, "error_message"),
            error_type=_required_field(fields, "error_type"),
        )


def _required_field(fields: Mapping[str, str], field_name: str) -> str:
    value = fields.get(field_name)
    if value is None or not value.strip():
        raise ValueError(f"Task completion event field '{field_name}' is required.")
    return value


def _parse_output_data(serialized_output: str) -> dict[str, object]:
    try:
        output_data = loads(serialized_output)
    except JSONDecodeError as error:
        raise ValueError("Task completion event field 'output_data' must contain JSON.") from error
    if not isinstance(output_data, dict):
        raise ValueError("Task completion event field 'output_data' must contain a JSON object.")
    return output_data
