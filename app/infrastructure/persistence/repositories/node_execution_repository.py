"""SQLAlchemy implementation of the node execution repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.execution import NodeExecution
from app.domain.repositories.node_execution_repository import NodeExecutionRepository
from app.domain.states import NodeExecutionStatus
from app.infrastructure.persistence.models.node_execution import NodeExecutionRecord


class SqlAlchemyNodeExecutionRepository(NodeExecutionRepository):
    """Node execution repository backed by SQLAlchemy/PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_node_executions_for_execution(self, execution_id: UUID) -> list[NodeExecution]:
        result = await self._session.execute(
            select(NodeExecutionRecord).where(
                NodeExecutionRecord.workflow_execution_id == execution_id
            )
        )
        records = result.scalars().all()
        return [
            NodeExecution.model_validate(
                {
                    "workflow_execution_id": record.workflow_execution_id,
                    "node_id": record.node_id,
                    "status": NodeExecutionStatus(record.status),
                    "output_data": record.output_data,
                    "error_message": record.error_message,
                    "error_type": record.error_type,
                    "created_at": record.created_at,
                    "started_at": record.started_at,
                    "completed_at": record.completed_at,
                }
            )
            for record in records
        ]

    async def upsert_node_execution(self, node_execution: NodeExecution) -> NodeExecution:
        statement = insert(NodeExecutionRecord).values(
            workflow_execution_id=node_execution.workflow_execution_id,
            node_id=node_execution.node_id,
            status=node_execution.status.value,
            output_data=node_execution.output_data,
            error_message=node_execution.error_message,
            error_type=node_execution.error_type,
            created_at=node_execution.created_at,
            started_at=node_execution.started_at,
            completed_at=node_execution.completed_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                NodeExecutionRecord.workflow_execution_id,
                NodeExecutionRecord.node_id,
            ],
            set_={
                "status": node_execution.status.value,
                "output_data": node_execution.output_data,
                "error_message": node_execution.error_message,
                "error_type": node_execution.error_type,
                "started_at": node_execution.started_at,
                "completed_at": node_execution.completed_at,
            },
        )
        await self._session.execute(statement)
        return node_execution

    async def update_status_if_current(
        self,
        execution_id: UUID,
        node_id: str,
        expected_current_status: NodeExecutionStatus,
        new_status: NodeExecutionStatus,
        *,
        output_data: dict[str, object] | None = None,
        error_message: str | None = None,
        error_type: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        values: dict[str, Any] = {"status": new_status.value}
        if output_data is not None:
            values["output_data"] = output_data
        if error_message is not None:
            values["error_message"] = error_message
        if error_type is not None:
            values["error_type"] = error_type
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at

        result = await self._session.execute(
            update(NodeExecutionRecord)
            .where(NodeExecutionRecord.workflow_execution_id == execution_id)
            .where(NodeExecutionRecord.node_id == node_id)
            .where(NodeExecutionRecord.status == expected_current_status.value)
            .values(**values)
            .returning(NodeExecutionRecord.workflow_execution_id)
        )
        return result.scalar_one_or_none() is not None
