"""SQLAlchemy implementation of the workflow repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.workflow_repository import WorkflowRepository
from app.domain.workflow import Workflow
from app.infrastructure.persistence.models.workflow import WorkflowRecord


class SqlAlchemyWorkflowRepository(WorkflowRepository):
    """Workflow repository backed by SQLAlchemy/PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_workflow(self, workflow: Workflow) -> Workflow:
        record = WorkflowRecord(
            workflow_id=workflow.workflow_id,
            name=workflow.name,
            dag_definition={"nodes": [node.model_dump(mode="json") for node in workflow.nodes]},
            created_at=workflow.created_at,
        )
        self._session.add(record)
        return workflow

    async def get_workflow_by_id(self, workflow_id: UUID) -> Workflow | None:
        result = await self._session.execute(
            select(WorkflowRecord).where(WorkflowRecord.workflow_id == workflow_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        nodes_payload = record.dag_definition.get("nodes", [])
        return Workflow.model_validate(
            {
                "workflow_id": record.workflow_id,
                "name": record.name,
                "nodes": nodes_payload,
                "created_at": record.created_at,
            }
        )
