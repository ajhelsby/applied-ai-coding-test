"""Shared node handler interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.messaging.task_messages import NodeTaskMessage


class NodeHandler(ABC):
    """Execute a supported workflow node task."""

    @abstractmethod
    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        """Return the task output."""

        raise NotImplementedError
