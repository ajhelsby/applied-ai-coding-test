"""Unit tests for independent workflow validation rules."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.domain.validation.rules import (
    CycleDetectionRule,
    DependencyReferencesRule,
    HandlerDefinitionRule,
    NodeConfigurationRule,
    NodeIdValidityRule,
    RequiredNodeFieldsRule,
    RequiredWorkflowFieldsRule,
    SelfDependencyRule,
    UniqueNodeIdsRule,
)


def valid_workflow() -> dict[str, Any]:
    return {
        "name": "Parallel API Fetcher",
        "dag": {
            "nodes": [
                {"id": "input", "handler": "input", "dependencies": []},
                {
                    "id": "get_user",
                    "handler": "call_external_service",
                    "dependencies": ["input"],
                    "config": {"url": "https://example.test/users"},
                },
                {
                    "id": "get_posts",
                    "handler": "call_external_service",
                    "dependencies": ["input"],
                    "config": {"url": "https://example.test/posts"},
                },
                {
                    "id": "output",
                    "handler": "output",
                    "dependencies": ["get_user", "get_posts"],
                },
            ]
        },
    }


@pytest.mark.parametrize(
    ("workflow", "code"),
    [
        ({}, "required_workflow_name"),
        ({"name": "workflow"}, "required_workflow_dag"),
        ({"name": "workflow", "dag": {}}, "required_workflow_nodes"),
    ],
)
def test_required_workflow_fields_rule_reports_missing_or_invalid_properties(
    workflow: dict[str, Any], code: str
) -> None:
    assert RequiredWorkflowFieldsRule().validate(workflow)[0].code == code


@pytest.mark.parametrize(
    ("node", "code"),
    [
        ({"handler": "input", "dependencies": []}, "required_node_id"),
        ({"id": "input", "dependencies": []}, "required_node_handler"),
        ({"id": "input", "handler": "input"}, "required_node_dependencies"),
        (
            {"id": "input", "handler": "input", "dependencies": "not-a-list"},
            "invalid_node_dependencies",
        ),
    ],
)
def test_required_node_fields_rule_reports_invalid_node_properties(
    node: dict[str, Any], code: str
) -> None:
    workflow = {"name": "workflow", "dag": {"nodes": [node]}}

    assert RequiredNodeFieldsRule().validate(workflow)[0].code == code


def test_required_node_fields_rule_rejects_non_object_nodes() -> None:
    workflow = {"name": "workflow", "dag": {"nodes": ["not-a-node"]}}

    assert RequiredNodeFieldsRule().validate(workflow)[0].code == "invalid_node_definition"


@pytest.mark.parametrize("node_id", ["", " ", "1start", "invalid id", "invalid.id"])
def test_node_id_validity_rule_rejects_invalid_identifiers(node_id: str) -> None:
    workflow = valid_workflow()
    workflow["dag"]["nodes"][0]["id"] = node_id

    errors = NodeIdValidityRule().validate(workflow)

    assert errors[0].code == "invalid_node_id"
    assert errors[0].path == "dag.nodes[0].id"


def test_unique_node_ids_rule_reports_each_duplicate() -> None:
    workflow = valid_workflow()
    workflow["dag"]["nodes"][1]["id"] = "input"

    errors = UniqueNodeIdsRule().validate(workflow)

    assert [error.code for error in errors] == ["duplicate_node_id", "duplicate_node_id"]
    assert {error.node_id for error in errors} == {"input"}


@pytest.mark.parametrize("handler", ["", "unknown_handler", None])
def test_handler_definition_rule_rejects_unsupported_handlers(handler: object) -> None:
    workflow = valid_workflow()
    workflow["dag"]["nodes"][0]["handler"] = handler

    errors = HandlerDefinitionRule().validate(workflow)

    assert errors[0].code == "invalid_handler"
    assert errors[0].node_id == "input"


@pytest.mark.parametrize(
    ("node", "code"),
    [
        (
            {
                "id": "fetch",
                "handler": "call_external_service",
                "dependencies": [],
            },
            "invalid_handler_config",
        ),
        (
            {
                "id": "fetch",
                "handler": "call_external_service",
                "dependencies": [],
                "config": {"url": ""},
            },
            "invalid_handler_config",
        ),
        (
            {
                "id": "input",
                "handler": "input",
                "dependencies": [],
                "config": {"unexpected": "value"},
            },
            "invalid_handler_config",
        ),
    ],
)
def test_node_configuration_rule_enforces_handler_contracts(
    node: dict[str, Any], code: str
) -> None:
    workflow = {"name": "workflow", "dag": {"nodes": [node]}}

    assert NodeConfigurationRule().validate(workflow)[0].code == code


def test_dependency_references_rule_rejects_unknown_dependencies() -> None:
    workflow = valid_workflow()
    workflow["dag"]["nodes"][1]["dependencies"] = ["missing"]

    error = DependencyReferencesRule().validate(workflow)[0]

    assert error.code == "unknown_dependency"
    assert error.node_id == "get_user"
    assert error.dependency_id == "missing"


def test_self_dependency_rule_rejects_self_references() -> None:
    workflow = valid_workflow()
    workflow["dag"]["nodes"][1]["dependencies"] = ["get_user"]

    error = SelfDependencyRule().validate(workflow)[0]

    assert error.code == "self_dependency"
    assert error.node_id == "get_user"
    assert error.dependency_id == "get_user"


def test_cycle_detection_rule_rejects_cycles() -> None:
    workflow = valid_workflow()
    workflow["dag"]["nodes"][0]["dependencies"] = ["output"]

    error = CycleDetectionRule().validate(workflow)[0]

    assert error.code == "cyclic_dependency"
    assert error.node_id is not None
    assert error.dependency_id is not None


@pytest.mark.parametrize(
    "rule",
    [
        RequiredWorkflowFieldsRule(),
        RequiredNodeFieldsRule(),
        NodeIdValidityRule(),
        UniqueNodeIdsRule(),
        HandlerDefinitionRule(),
        NodeConfigurationRule(),
        DependencyReferencesRule(),
        SelfDependencyRule(),
        CycleDetectionRule(),
    ],
)
def test_rules_accept_valid_fan_out_fan_in_workflow(rule: object) -> None:
    assert rule.validate(valid_workflow()) == []


def test_rules_do_not_mutate_workflow() -> None:
    workflow = valid_workflow()
    original = deepcopy(workflow)

    for rule in (
        RequiredWorkflowFieldsRule(),
        RequiredNodeFieldsRule(),
        NodeIdValidityRule(),
        UniqueNodeIdsRule(),
        HandlerDefinitionRule(),
        NodeConfigurationRule(),
        DependencyReferencesRule(),
        SelfDependencyRule(),
        CycleDetectionRule(),
    ):
        rule.validate(workflow)

    assert workflow == original
