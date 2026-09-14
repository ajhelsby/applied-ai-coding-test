"""Node handler resolution and task execution."""

from __future__ import annotations

from collections.abc import Mapping

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler
from app.worker.handlers.external_service import MockExternalServiceNodeHandler
from app.worker.handlers.input import InputNodeHandler
from app.worker.handlers.mock_llm import MockLlmServiceNodeHandler
from app.worker.handlers.output import OutputNodeHandler


class UnknownNodeHandlerError(ValueError):
    """Raised when no worker handler is registered for a task."""


class NodeHandlerRegistry:
    """Resolve task handler identifiers to asynchronous implementations."""

    def __init__(self, handlers: Mapping[str, NodeHandler] | None = None) -> None:
        self._handlers = dict(handlers) if handlers is not None else None

    def resolve(self, handler_name: str) -> NodeHandler:
        """Return the handler registered for a task's handler identifier."""

        if self._handlers is not None:
            try:
                return self._handlers[handler_name]
            except KeyError as error:
                raise UnknownNodeHandlerError(
                    f"No worker handler is registered for '{handler_name}'."
                ) from error

        match handler_name:
            case "input":
                return InputNodeHandler()
            case "output":
                return OutputNodeHandler()
            case "call_external_service":
                return MockExternalServiceNodeHandler()
            case "llm_service":
                return MockLlmServiceNodeHandler()
            case _:
                raise UnknownNodeHandlerError(
                    f"No worker handler is registered for '{handler_name}'."
                )


class WorkerTaskExecutor:
    """Resolve and execute one validated worker task."""

    def __init__(self, handler_registry: NodeHandlerRegistry | None = None) -> None:
        self._handler_registry = handler_registry or NodeHandlerRegistry()

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        """Execute the task using its registered handler."""

        handler = self._handler_registry.resolve(task.handler)
        return await handler.execute(task)
