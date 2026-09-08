"""Domain-level workflow validation contracts and orchestrator."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.domain.errors.validation import WorkflowValidationError


class WorkflowValidationRule(Protocol):
    """Contract for independent workflow validation rules."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        """Validate a workflow and return any domain errors."""


class WorkflowValidator:
    """Runs configured validation rules and aggregates all errors."""

    def __init__(self, rules: Sequence[WorkflowValidationRule]) -> None:
        self._rules = tuple(rules)

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        errors: list[WorkflowValidationError] = []
        for rule in self._rules:
            errors.extend(rule.validate(workflow))
        return errors


class WorkflowRuleProvider(Protocol):
    """Contract for producing workflow validation rules."""

    def get_rules(self) -> list[WorkflowValidationRule]:
        """Return validation rules in deterministic execution order."""


class DefaultWorkflowRuleProvider:
    """Default provider for built-in workflow validation rules."""

    def get_rules(self) -> list[WorkflowValidationRule]:
        from app.domain.validation.rules.cycles import CycleDetectionRule
        from app.domain.validation.rules.dependencies import (
            DependencyReferenceRule,
        )
        from app.domain.validation.rules.fields import (
            RequiredNodeFieldsRule,
            RequiredWorkflowFieldsRule,
        )
        from app.domain.validation.rules.handlers import (
            HandlerDefinitionRule,
            NodeConfigurationRule,
        )
        from app.domain.validation.rules.node_ids import (
            NodeIdValidityRule,
            UniqueNodeIdsRule,
        )

        return [
            RequiredWorkflowFieldsRule(),
            RequiredNodeFieldsRule(),
            NodeIdValidityRule(),
            UniqueNodeIdsRule(),
            HandlerDefinitionRule(),
            NodeConfigurationRule(),
            DependencyReferenceRule(),
            CycleDetectionRule(),
        ]


def collect_rules(
    providers: Sequence[WorkflowRuleProvider],
) -> list[WorkflowValidationRule]:
    """Collect rules from providers in provider order."""

    rules: list[WorkflowValidationRule] = []
    for provider in providers:
        rules.extend(provider.get_rules())
    return rules
