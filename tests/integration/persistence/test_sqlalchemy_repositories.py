"""Integration coverage for PostgreSQL workflow persistence adapters."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.execution import NodeExecution, WorkflowExecution
from app.domain.node import WorkflowNode
from app.domain.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.domain.workflow import Workflow
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL is required to run PostgreSQL persistence integration tests.",
    ),
]


@pytest.fixture
def session_factory() -> Iterator[async_sessionmaker[AsyncSession]]:
    """Create a connection factory for the compose PostgreSQL database."""
    engine = create_async_engine(DATABASE_URL)
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


def test_persists_and_retrieves_workflow_execution_and_nodes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def scenario() -> None:
        workflow = Workflow(
            name="document-processing",
            nodes=[
                WorkflowNode(
                    node_id="extract",
                    handler="extract_document",
                    config={"format": "pdf", "pages": [1, 2]},
                )
            ],
        )
        execution = WorkflowExecution(
            workflow_id=workflow.workflow_id,
            input_data={"document_id": "doc-123", "metadata": {"source": "upload"}},
        )
        node_execution = NodeExecution(
            workflow_execution_id=execution.execution_id,
            node_id="extract",
            output_data={"text": "Extracted content", "confidence": 0.98},
        )
        uow = SqlAlchemyUnitOfWork(session_factory)

        async with uow.transaction() as transaction:
            await transaction.workflows.create_workflow(workflow)
            await transaction.workflow_executions.create_execution(execution)
            await transaction.node_executions.upsert_node_execution(node_execution)

        async with uow.transaction() as transaction:
            assert await transaction.workflows.get_workflow_by_id(workflow.workflow_id) == workflow
            assert (
                await transaction.workflow_executions.get_execution_by_id(execution.execution_id)
                == execution
            )
            assert await transaction.node_executions.get_node_executions_for_execution(
                execution.execution_id
            ) == [node_execution]

    asyncio.run(scenario())


def test_updates_execution_states_only_when_expected_status_matches(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def scenario() -> None:
        workflow = Workflow(name="state-transition")
        execution = WorkflowExecution(workflow_id=workflow.workflow_id)
        node_execution = NodeExecution(
            workflow_execution_id=execution.execution_id,
            node_id="first-node",
        )
        started_at = datetime.now(UTC)
        completed_at = datetime.now(UTC)
        uow = SqlAlchemyUnitOfWork(session_factory)

        async with uow.transaction() as transaction:
            await transaction.workflows.create_workflow(workflow)
            await transaction.workflow_executions.create_execution(execution)
            await transaction.node_executions.upsert_node_execution(node_execution)

        async with uow.transaction() as transaction:
            assert await transaction.workflow_executions.update_status_if_current(
                execution.execution_id,
                WorkflowExecutionStatus.PENDING,
                WorkflowExecutionStatus.RUNNING,
                started_at=started_at,
            )
            assert not await transaction.workflow_executions.update_status_if_current(
                execution.execution_id,
                WorkflowExecutionStatus.PENDING,
                WorkflowExecutionStatus.COMPLETED,
                completed_at=completed_at,
            )
            assert await transaction.node_executions.update_status_if_current(
                execution.execution_id,
                node_execution.node_id,
                NodeExecutionStatus.PENDING,
                NodeExecutionStatus.COMPLETED,
                output_data={"result": {"items": 3}},
                completed_at=completed_at,
            )
            assert not await transaction.node_executions.update_status_if_current(
                execution.execution_id,
                node_execution.node_id,
                NodeExecutionStatus.PENDING,
                NodeExecutionStatus.FAILED,
            )

        async with uow.transaction() as transaction:
            persisted_execution = await transaction.workflow_executions.get_execution_by_id(
                execution.execution_id
            )
            persisted_nodes = await transaction.node_executions.get_node_executions_for_execution(
                execution.execution_id
            )
            assert persisted_execution is not None
            assert persisted_execution.status is WorkflowExecutionStatus.RUNNING
            assert persisted_execution.started_at == started_at
            assert persisted_nodes[0].status is NodeExecutionStatus.COMPLETED
            assert persisted_nodes[0].output_data == {"result": {"items": 3}}
            assert persisted_nodes[0].completed_at == completed_at

    asyncio.run(scenario())


def test_rolls_back_related_writes_when_a_transaction_fails(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def scenario() -> None:
        workflow = Workflow(name="rollback")
        uow = SqlAlchemyUnitOfWork(session_factory)

        with pytest.raises(RuntimeError, match="force rollback"):
            async with uow.transaction() as transaction:
                await transaction.workflows.create_workflow(workflow)
                raise RuntimeError("force rollback")

        async with uow.transaction() as transaction:
            assert await transaction.workflows.get_workflow_by_id(workflow.workflow_id) is None

    asyncio.run(scenario())
