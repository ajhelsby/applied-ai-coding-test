"""Mock external service node handler implementation."""

from __future__ import annotations

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler


class MockExternalServiceNodeHandler(NodeHandler):
    """Return a deterministic response until external integration is implemented."""

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        url = task.handler_config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Handler 'call_external_service' requires a non-empty config.url.")
        return {
            "status": "mocked",
            "url": url,
            "input": dict(task.resolved_input),
        }
