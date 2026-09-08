"""Worker task message contracts and stream-message parsing."""

from __future__ import annotations

from collections.abc import Mapping
from json import dumps
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.messaging.stream_fields import json_object_field, required_field


class NodeTaskMessage(BaseModel):
    """A dispatched workflow node execution task consumed by workers."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    execution_id: UUID
    node_id: str = Field(min_length=1)
    handler: str = Field(min_length=1)
    handler_config: dict[str, object]
    resolved_input: dict[str, object]

    @classmethod
    def from_stream_fields(cls, fields: Mapping[str, str]) -> NodeTaskMessage:
        """Parse and validate a flat Redis stream task message."""

        return cls.model_validate(
            {
                "task_id": required_field(fields, "task_id", "Task message"),
                "execution_id": required_field(fields, "execution_id", "Task message"),
                "node_id": required_field(fields, "node_id", "Task message"),
                "handler": required_field(fields, "handler", "Task message"),
                "handler_config": json_object_field(fields, "handler_config", "Task message"),
                "resolved_input": json_object_field(fields, "resolved_input", "Task message"),
            }
        )

    def to_stream_fields(self) -> dict[str, str]:
        """Serialize task message fields for publishing to Redis Streams."""

        return {
            "task_id": self.task_id,
            "execution_id": str(self.execution_id),
            "node_id": self.node_id,
            "handler": self.handler,
            "handler_config": dumps(self.handler_config, separators=(",", ":"), sort_keys=True),
            "resolved_input": dumps(self.resolved_input, separators=(",", ":"), sort_keys=True),
        }
