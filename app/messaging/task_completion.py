"""Worker task completion event contract and stream-message parsing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from json import dumps
from uuid import UUID

from app.messaging.stream_fields import json_object_field, required_field


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

    def to_stream_fields(self) -> dict[str, str]:
        """Serialize the completion event for publishing to Redis Streams."""

        fields = {
            "event_id": str(self.event_id),
            "task_id": self.task_id,
            "execution_id": str(self.execution_id),
            "node_id": self.node_id,
            "status": self.status.value,
        }
        if self.status is TaskCompletionStatus.COMPLETED:
            if self.output_data is None:
                raise ValueError("Completed task completion events require output_data.")
            return {
                **fields,
                "output_data": dumps(self.output_data, separators=(",", ":"), sort_keys=True),
            }
        if self.error_message is None or self.error_type is None:
            raise ValueError("Failed task completion events require error information.")
        return {
            **fields,
            "error_message": self.error_message,
            "error_type": self.error_type,
        }

    @classmethod
    def from_stream_fields(cls, fields: Mapping[str, str]) -> TaskCompletionEvent:
        """Parse and validate a flat Redis stream completion event."""

        event_id = UUID(required_field(fields, "event_id", "Task completion event"))
        task_id = required_field(fields, "task_id", "Task completion event")
        execution_id = UUID(required_field(fields, "execution_id", "Task completion event"))
        node_id = required_field(fields, "node_id", "Task completion event")
        status = TaskCompletionStatus(required_field(fields, "status", "Task completion event"))

        if status is TaskCompletionStatus.COMPLETED:
            output_data = json_object_field(fields, "output_data", "Task completion event")
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
            error_message=required_field(fields, "error_message", "Task completion event"),
            error_type=required_field(fields, "error_type", "Task completion event"),
        )
