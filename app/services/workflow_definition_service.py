"""Application service for accepting workflow definitions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.errors.validation import InvalidWorkflowDefinitionError
from app.domain.models.execution import WorkflowExecution
from app.domain.models.workflow import Workflow
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.validation import (
    DefaultWorkflowRuleProvider,
    WorkflowRuleProvider,
    WorkflowValidator,
    collect_rules,
)


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
            raise InvalidWorkflowDefinitionError(errors)
        return Workflow.model_validate(definition)

    async def submit(
        self,
        definition: Mapping[str, Any],
        unit_of_work: UnitOfWork,
    ) -> WorkflowExecution:
        """Accept a definition and create its pending workflow execution."""

        workflow = self.accept(definition)
        execution = WorkflowExecution(workflow_id=workflow.workflow_id)
        async with unit_of_work.transaction() as transaction:
            await transaction.workflows.create_workflow(workflow)
            await transaction.workflow_executions.create_execution(execution)
        return execution
