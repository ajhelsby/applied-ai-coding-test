"""Unit tests for workflow validator composition and aggregation."""

from __future__ import annotations

from typing import Any

import pytest

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


@pytest.mark.parametrize(
    "nodes",
    [
        [
            {"id": "root-a", "handler": "input", "dependencies": []},
            {"id": "root-b", "handler": "input", "dependencies": []},
            {"id": "left", "handler": "output", "dependencies": ["root-a"]},
            {"id": "right", "handler": "output", "dependencies": ["root-b"]},
        ],
        [
            {"id": "root", "handler": "input", "dependencies": []},
            {"id": "left", "handler": "output", "dependencies": ["root"]},
            {"id": "right", "handler": "output", "dependencies": ["root"]},
            {"id": "join", "handler": "output", "dependencies": ["left", "right"]},
        ],
    ],
)
def test_default_validator_accepts_valid_branching_dags(
    nodes: list[dict[str, Any]],
) -> None:
    workflow = {"name": "branching-workflow", "dag": {"nodes": nodes}}

    errors = WorkflowValidator(DefaultWorkflowRuleProvider().get_rules()).validate(workflow)

    assert errors == []


def test_default_validator_aggregates_structured_errors_for_malformed_workflow() -> None:
    workflow = {
        "name": "malformed-workflow",
        "dag": {
            "nodes": [
                {
                    "id": "root",
                    "handler": "input",
                    "dependencies": ["missing"],
                },
                {
                    "id": "root",
                    "handler": "output",
                    "dependencies": ["root"],
                },
            ]
        },
    }

    errors = WorkflowValidator(DefaultWorkflowRuleProvider().get_rules()).validate(workflow)

    assert [error.code for error in errors] == [
        "duplicate_node_id",
        "duplicate_node_id",
        "unknown_dependency",
        "self_dependency",
    ]
    assert [(error.node_id, error.dependency_id) for error in errors] == [
        ("root", None),
        ("root", None),
        ("root", "missing"),
        ("root", "root"),
    ]


def test_default_validator_reports_missing_dependency_with_context() -> None:
    workflow = {
        "name": "missing-dependency",
        "dag": {
            "nodes": [
                {"id": "root", "handler": "input", "dependencies": []},
                {"id": "child", "handler": "output", "dependencies": ["unknown"]},
            ]
        },
    }

    errors = WorkflowValidator(DefaultWorkflowRuleProvider().get_rules()).validate(workflow)

    assert len(errors) == 1
    assert errors[0].code == "unknown_dependency"
    assert errors[0].path == "dag.nodes[1].dependencies[0]"
    assert errors[0].node_id == "child"
    assert errors[0].dependency_id == "unknown"
