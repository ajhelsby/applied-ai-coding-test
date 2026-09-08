"""Async node handlers and resolution for worker task execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.messaging.task_messages import NodeTaskMessage


class NodeHandler(Protocol):
    """Execute a supported workflow node task."""

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        """Return the task output."""


class UnknownNodeHandlerError(ValueError):
    """Raised when no worker handler is registered for a task."""


class InputNodeHandler:
    """Pass resolved workflow input into the workflow."""

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        return dict(task.resolved_input)


class OutputNodeHandler:
    """Expose resolved workflow data as the workflow output."""

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        return dict(task.resolved_input)


class MockExternalServiceNodeHandler:
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


class NodeHandlerRegistry:
    """Resolve task handler identifiers to asynchronous implementations."""

    def __init__(self, handlers: Mapping[str, NodeHandler] | None = None) -> None:
        self._handlers: dict[str, NodeHandler]
        if handlers is None:
            self._handlers = {
                "input": InputNodeHandler(),
                "output": OutputNodeHandler(),
                "call_external_service": MockExternalServiceNodeHandler(),
            }
        else:
            self._handlers = dict(handlers)

    def resolve(self, handler_name: str) -> NodeHandler:
        """Return the handler registered for a task's handler identifier."""

        try:
            return self._handlers[handler_name]
        except KeyError as error:
            raise UnknownNodeHandlerError(
                f"No worker handler is registered for '{handler_name}'."
            ) from error


class WorkerTaskExecutor:
    """Resolve and execute one validated worker task."""

    def __init__(self, handler_registry: NodeHandlerRegistry | None = None) -> None:
        self._handler_registry = handler_registry or NodeHandlerRegistry()

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        """Execute the task using its registered handler."""

        handler = self._handler_registry.resolve(task.handler)
        return await handler.execute(task)
