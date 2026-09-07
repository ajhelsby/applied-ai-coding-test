"""Unit-of-work contract for transactional persistence operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.repositories.node_execution_repository import NodeExecutionRepository
from app.domain.repositories.workflow_execution_repository import WorkflowExecutionRepository
from app.domain.repositories.workflow_repository import WorkflowRepository


class UnitOfWork(Protocol):
    """Transaction boundary and repository access for persistence operations."""

    workflows: WorkflowRepository
    workflow_executions: WorkflowExecutionRepository
    node_executions: NodeExecutionRepository

    def transaction(self) -> AsyncIterator[UnitOfWork]:
        """Provide a managed transactional scope."""
