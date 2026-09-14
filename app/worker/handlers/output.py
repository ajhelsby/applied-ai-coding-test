"""Output node handler implementation."""

from __future__ import annotations

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler


class OutputNodeHandler(NodeHandler):
    """Return the dependency-ID-keyed aggregate resolved by the orchestrator."""

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        return dict(task.resolved_input)
