"""Application service for accepting workflow definitions."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.dag import DAG
from app.domain.errors.validation import InvalidWorkflowDefinitionError
from app.domain.models.workflow import Workflow
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.validation import (
    DefaultWorkflowRuleProvider,
    WorkflowRuleProvider,
    WorkflowValidator,
    collect_rules,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkflowSubmission:
    """Workflow metadata returned after a successful submission."""

    execution_id: UUID
    name: str
    created_at: datetime


class WorkflowDefinitionService:
    """Validate workflow definitions before accepting them for later execution."""

    def __init__(
        self,
        rule_providers: Sequence[WorkflowRuleProvider] | None = None,
    ) -> None:
        providers = (
            list(rule_providers) if rule_providers is not None else [DefaultWorkflowRuleProvider()]
        )
        self._validator = WorkflowValidator(collect_rules(providers))

    def accept(self, definition: Mapping[str, Any]) -> Workflow:
        """Validate and construct an accepted workflow definition."""

        errors = self._validator.validate(definition)
        if errors:
            logger.warning(
                "Workflow submission validation failed", extra={"error_count": len(errors)}
            )
            raise InvalidWorkflowDefinitionError(errors)
        return Workflow.model_validate(definition)

    def build_dag(self, definition: Mapping[str, Any]) -> DAG:
        """Validate a workflow definition and construct its traversal graph."""

        return DAG.from_workflow(self.accept(definition))

    async def submit(
        self,
        definition: Mapping[str, Any],
        unit_of_work: UnitOfWork,
    ) -> WorkflowSubmission:
        """Validate and persist a workflow definition without starting execution."""

        workflow = self.accept(definition)
        async with unit_of_work.transaction() as transaction:
            await transaction.workflows.create_workflow(workflow)
        logger.info("Workflow submitted", extra={"workflow_id": str(workflow.workflow_id)})
        return WorkflowSubmission(
            execution_id=workflow.workflow_id,
            name=workflow.name,
            created_at=workflow.created_at,
        )
