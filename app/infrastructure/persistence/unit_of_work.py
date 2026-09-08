"""SQLAlchemy unit-of-work implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionFactory
from app.domain.errors.persistence import WorkflowPersistenceError
from app.domain.repositories.node_execution_repository import NodeExecutionRepository
from app.domain.repositories.outbox_event_repository import OutboxEventRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.repositories.workflow_execution_repository import WorkflowExecutionRepository
from app.domain.repositories.workflow_repository import WorkflowRepository
from app.infrastructure.persistence.repositories import (
    SqlAlchemyNodeExecutionRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyWorkflowExecutionRepository,
    SqlAlchemyWorkflowRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Managed transaction boundary over a shared SQLAlchemy session."""

    def __init__(self, session_factory: Callable[[], AsyncSession] = AsyncSessionFactory) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.workflows: WorkflowRepository = cast(WorkflowRepository, _UnavailableRepository())
        self.workflow_executions: WorkflowExecutionRepository = cast(
            WorkflowExecutionRepository, _UnavailableRepository()
        )
        self.node_executions: NodeExecutionRepository = cast(
            NodeExecutionRepository, _UnavailableRepository()
        )
        self.outbox_events: OutboxEventRepository = cast(
            OutboxEventRepository, _UnavailableRepository()
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlAlchemyUnitOfWork]:
        async with self._session_factory() as session:
            self._session = session
            self.workflows = SqlAlchemyWorkflowRepository(session)
            self.workflow_executions = SqlAlchemyWorkflowExecutionRepository(session)
            self.node_executions = SqlAlchemyNodeExecutionRepository(session)
            self.outbox_events = SqlAlchemyOutboxEventRepository(session)
            try:
                yield self
                await session.commit()
            except SQLAlchemyError as error:
                await session.rollback()
                raise WorkflowPersistenceError("Unable to persist workflow data.") from error
            except Exception:
                await session.rollback()
                raise
            finally:
                self._session = None
                self.workflows = cast(WorkflowRepository, _UnavailableRepository())
                self.workflow_executions = cast(
                    WorkflowExecutionRepository, _UnavailableRepository()
                )
                self.node_executions = cast(NodeExecutionRepository, _UnavailableRepository())
                self.outbox_events = cast(OutboxEventRepository, _UnavailableRepository())


class _UnavailableRepository:
    """Sentinel repository used outside of an active transaction scope."""

    def __getattr__(self, name: str) -> object:
        del name
        raise RuntimeError("Repositories are available only inside 'async with uow.transaction()'.")
