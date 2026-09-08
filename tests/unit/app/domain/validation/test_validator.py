"""Unit tests for workflow validator composition and aggregation."""

from __future__ import annotations

from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation import (
    DefaultWorkflowRuleProvider,
    WorkflowValidator,
    collect_rules,
)


class StubRule:
    def __init__(self, code: str) -> None:
        self._code = code

    def validate(self, workflow: dict[str, Any]) -> list[WorkflowValidationError]:
        return [
            WorkflowValidationError(
                code=self._code,
                message=self._code,
                path="workflow",
            )
        ]


class StubProvider:
    def __init__(self, *rules: StubRule) -> None:
        self._rules = rules

    def get_rules(self) -> list[StubRule]:
        return list(self._rules)


def test_validator_aggregates_errors_in_rule_order() -> None:
    validator = WorkflowValidator([StubRule("first"), StubRule("second")])

    errors = validator.validate({})

    assert [error.code for error in errors] == ["first", "second"]


def test_collect_rules_preserves_provider_and_rule_order() -> None:
    rules = collect_rules([StubProvider(StubRule("first")), StubProvider(StubRule("second"))])

    errors = WorkflowValidator(rules).validate({})

    assert [error.code for error in errors] == ["first", "second"]


def test_default_provider_registers_all_initial_rules() -> None:
    assert len(DefaultWorkflowRuleProvider().get_rules()) == 8


def test_default_validator_accepts_valid_linear_dag() -> None:
    workflow = {
        "name": "linear-workflow",
        "dag": {
            "nodes": [
                {"id": "input", "handler": "input", "dependencies": []},
                {
                    "id": "fetch",
                    "handler": "call_external_service",
                    "dependencies": ["input"],
                    "config": {"url": "https://example.test"},
                },
                {"id": "output", "handler": "output", "dependencies": ["fetch"]},
            ]
        },
    }

    errors = WorkflowValidator(DefaultWorkflowRuleProvider().get_rules()).validate(workflow)

    assert errors == []
