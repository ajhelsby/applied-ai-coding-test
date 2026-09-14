"""Input node handler implementation."""

from __future__ import annotations

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler


class InputNodeHandler(NodeHandler):
    """Pass resolved workflow input into the workflow."""

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        return dict(task.resolved_input)
