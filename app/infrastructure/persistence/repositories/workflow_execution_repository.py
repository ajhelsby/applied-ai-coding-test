"""SQLAlchemy implementation of the workflow execution repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.execution import WorkflowExecution
from app.domain.repositories.workflow_execution_repository import WorkflowExecutionRepository
from app.domain.state.states import WorkflowExecutionStatus
from app.infrastructure.persistence.models.workflow_execution import WorkflowExecutionRecord


class SqlAlchemyWorkflowExecutionRepository(WorkflowExecutionRepository):
    """Workflow execution repository backed by SQLAlchemy/PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_execution(self, execution: WorkflowExecution) -> WorkflowExecution:
        record = WorkflowExecutionRecord(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status.value,
            input_data=execution.input_data,
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
        )
        self._session.add(record)
        return execution

    async def get_execution_by_id(self, execution_id: UUID) -> WorkflowExecution | None:
        result = await self._session.execute(
            select(WorkflowExecutionRecord).where(
                WorkflowExecutionRecord.execution_id == execution_id
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        return WorkflowExecution.model_validate(
            {
                "execution_id": record.execution_id,
                "workflow_id": record.workflow_id,
                "status": WorkflowExecutionStatus(record.status),
                "input_data": record.input_data,
                "created_at": record.created_at,
                "started_at": record.started_at,
                "completed_at": record.completed_at,
            }
        )

    async def update_status_if_current(
        self,
        execution_id: UUID,
        expected_current_status: WorkflowExecutionStatus,
        new_status: WorkflowExecutionStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        input_data: dict[str, object] | None = None,
    ) -> bool:
        values: dict[str, object] = {
            "status": new_status.value,
            "updated_at": func.now(),
        }
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        if input_data is not None:
            values["input_data"] = input_data

        result = await self._session.execute(
            update(WorkflowExecutionRecord)
            .where(WorkflowExecutionRecord.execution_id == execution_id)
            .where(WorkflowExecutionRecord.status == expected_current_status.value)
            .values(**values)
            .returning(WorkflowExecutionRecord.execution_id)
        )
        return result.scalar_one_or_none() is not None
