"""Unit tests for independent workflow validation rules."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.domain.validation.rules import (
    CycleDetectionRule,
    DependencyReferenceRule,
    HandlerDefinitionRule,
    NodeConfigurationRule,
    NodeIdValidityRule,
    RequiredNodeFieldsRule,
    RequiredWorkflowFieldsRule,
    UniqueNodeIdsRule,
)


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
def test_node_id_validity_rule_rejects_invalid_identifiers(
    node_id: str, valid_workflow: dict[str, Any]
) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][0]["id"] = node_id

    errors = NodeIdValidityRule().validate(workflow)

    assert errors[0].code == "invalid_node_id"
    assert errors[0].path == "dag.nodes[0].id"


def test_unique_node_ids_rule_reports_each_duplicate(valid_workflow: dict[str, Any]) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][1]["id"] = "input"

    errors = UniqueNodeIdsRule().validate(workflow)

    assert [error.code for error in errors] == ["duplicate_node_id", "duplicate_node_id"]
    assert {error.node_id for error in errors} == {"input"}


@pytest.mark.parametrize("handler", ["", "unknown_handler", None])
def test_handler_definition_rule_rejects_unsupported_handlers(
    handler: object, valid_workflow: dict[str, Any]
) -> None:
    workflow = valid_workflow
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
                "id": "generate",
                "handler": "llm_service",
                "dependencies": [],
            },
            "invalid_handler_config",
        ),
        (
            {
                "id": "generate",
                "handler": "llm_service",
                "dependencies": [],
                "config": {"prompt": " "},
            },
            "invalid_handler_config",
        ),
        (
            {
                "id": "generate",
                "handler": "llm_service",
                "dependencies": [],
                "config": {"prompt": 42},
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


def test_node_configuration_rule_allows_extra_llm_service_config_keys() -> None:
    workflow = {
        "name": "workflow",
        "dag": {
            "nodes": [
                {
                    "id": "generate",
                    "handler": "llm_service",
                    "dependencies": [],
                    "config": {"prompt": "Summarize this.", "temperature": 0.2},
                }
            ]
        },
    }

    assert NodeConfigurationRule().validate(workflow) == []


def test_handler_definition_rule_accepts_llm_service() -> None:
    workflow = {
        "name": "workflow",
        "dag": {
            "nodes": [
                {
                    "id": "generate",
                    "handler": "llm_service",
                    "dependencies": [],
                    "config": {"prompt": "Generate a response."},
                }
            ]
        },
    }

    assert HandlerDefinitionRule().validate(workflow) == []


def test_dependency_reference_rule_rejects_unknown_dependencies(
    valid_workflow: dict[str, Any],
) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][1]["dependencies"] = ["missing"]

    error = DependencyReferenceRule().validate(workflow)[0]

    assert error.code == "unknown_dependency"
    assert error.node_id == "get_user"
    assert error.dependency_id == "missing"


def test_dependency_reference_rule_rejects_self_references(valid_workflow: dict[str, Any]) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][1]["dependencies"] = ["get_user"]

    error = DependencyReferenceRule().validate(workflow)[0]

    assert error.code == "self_dependency"
    assert error.node_id == "get_user"
    assert error.dependency_id == "get_user"


def test_dependency_reference_rule_rejects_duplicate_dependencies(
    valid_workflow: dict[str, Any],
) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][3]["dependencies"] = ["get_user", "get_user"]

    error = DependencyReferenceRule().validate(workflow)[0]

    assert error.code == "duplicate_dependency"
    assert error.node_id == "output"
    assert error.dependency_id == "get_user"


def test_dependency_reference_rule_allows_cyclic_references_without_cycle_error(
    valid_workflow: dict[str, Any],
) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][0]["dependencies"] = ["output"]

    errors = DependencyReferenceRule().validate(workflow)

    assert all(error.code != "cyclic_dependency" for error in errors)


def test_dependency_reference_rule_reports_errors_in_deterministic_order(
    valid_workflow: dict[str, Any],
) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][1]["dependencies"] = ["missing", "get_user", "input", "input"]
    workflow["dag"]["nodes"][3]["dependencies"] = ["unknown_second"]

    errors = DependencyReferenceRule().validate(workflow)

    assert [(error.code, error.path) for error in errors] == [
        ("unknown_dependency", "dag.nodes[1].dependencies[0]"),
        ("self_dependency", "dag.nodes[1].dependencies[1]"),
        ("duplicate_dependency", "dag.nodes[1].dependencies[3]"),
        ("unknown_dependency", "dag.nodes[3].dependencies[0]"),
    ]


@pytest.mark.parametrize(
    "nodes",
    [
        [{"id": "root", "handler": "input", "dependencies": []}],
        [
            {"id": "left-root", "handler": "input", "dependencies": []},
            {"id": "left", "handler": "output", "dependencies": ["left-root"]},
            {"id": "right-root", "handler": "input", "dependencies": []},
            {"id": "right", "handler": "output", "dependencies": ["right-root"]},
        ],
        [
            {"id": "root", "handler": "input", "dependencies": []},
            {"id": "left", "handler": "output", "dependencies": ["root"]},
            {"id": "right", "handler": "output", "dependencies": ["root"]},
            {
                "id": "join",
                "handler": "output",
                "dependencies": ["left", "right"],
            },
        ],
    ],
)
def test_dependency_reference_rule_accepts_valid_dependency_shapes(
    nodes: list[dict[str, Any]],
) -> None:
    workflow = {"name": "valid-dependencies", "dag": {"nodes": nodes}}

    assert DependencyReferenceRule().validate(workflow) == []


def test_dependency_reference_rule_rejects_non_string_dependencies(
    valid_workflow: dict[str, Any],
) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][1]["dependencies"] = ["input", 42]

    error = DependencyReferenceRule().validate(workflow)[0]

    assert error.code == "unknown_dependency"
    assert error.path == "dag.nodes[1].dependencies[1]"
    assert error.node_id == "get_user"
    assert error.dependency_id is None


def test_required_node_fields_rule_rejects_empty_node_definitions() -> None:
    workflow = {"name": "empty-node", "dag": {"nodes": [{}]}}

    errors = RequiredNodeFieldsRule().validate(workflow)

    assert [error.code for error in errors] == [
        "required_node_id",
        "required_node_handler",
        "required_node_dependencies",
    ]
    assert all(error.path.startswith("dag.nodes[0].") for error in errors)


def test_cycle_detection_rule_rejects_cycles(valid_workflow: dict[str, Any]) -> None:
    workflow = valid_workflow
    workflow["dag"]["nodes"][0]["dependencies"] = ["output"]

    error = CycleDetectionRule().validate(workflow)[0]

    assert error.code == "cyclic_dependency"
    assert error.node_id is not None
    assert error.dependency_id is not None
    assert error.meta["cycle_path"] == "input->output->get_user->input"


def test_cycle_detection_rule_detects_direct_cycle_with_path() -> None:
    workflow = {
        "name": "direct-cycle",
        "dag": {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": ["B"]},
                {"id": "B", "handler": "output", "dependencies": ["A"]},
            ]
        },
    }

    errors = CycleDetectionRule().validate(workflow)

    assert len(errors) == 1
    assert errors[0].code == "cyclic_dependency"
    assert errors[0].meta["cycle_path"] == "A->B->A"


def test_cycle_detection_rule_detects_indirect_cycle_with_path() -> None:
    workflow = {
        "name": "indirect-cycle",
        "dag": {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": ["B"]},
                {"id": "B", "handler": "output", "dependencies": ["C"]},
                {"id": "C", "handler": "output", "dependencies": ["A"]},
            ]
        },
    }

    errors = CycleDetectionRule().validate(workflow)

    assert len(errors) == 1
    assert errors[0].code == "cyclic_dependency"
    assert errors[0].meta["cycle_path"] == "A->B->C->A"


def test_cycle_detection_rule_accepts_valid_linear_dag() -> None:
    workflow = {
        "name": "linear-dag",
        "dag": {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "output", "dependencies": ["A"]},
                {"id": "C", "handler": "output", "dependencies": ["B"]},
            ]
        },
    }

    assert CycleDetectionRule().validate(workflow) == []


def test_cycle_detection_rule_accepts_valid_fan_out_fan_in_dag() -> None:
    workflow = {
        "name": "fan-out-fan-in-dag",
        "dag": {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "output", "dependencies": ["A"]},
                {"id": "C", "handler": "output", "dependencies": ["A"]},
                {"id": "D", "handler": "output", "dependencies": ["B", "C"]},
            ]
        },
    }

    assert CycleDetectionRule().validate(workflow) == []


def test_cycle_detection_rule_handles_multiple_independent_branches() -> None:
    workflow = {
        "name": "independent-branches",
        "dag": {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "output", "dependencies": ["A"]},
                {"id": "X", "handler": "input", "dependencies": ["Y"]},
                {"id": "Y", "handler": "output", "dependencies": ["X"]},
            ]
        },
    }

    errors = CycleDetectionRule().validate(workflow)

    assert len(errors) == 1
    assert errors[0].code == "cyclic_dependency"
    assert errors[0].meta["cycle_path"] == "X->Y->X"


def test_cycle_detection_rule_rejects_cycle_with_valid_disconnected_branch() -> None:
    workflow = {
        "name": "valid-branch-and-cycle",
        "dag": {
            "nodes": [
                {"id": "root", "handler": "input", "dependencies": []},
                {"id": "valid", "handler": "output", "dependencies": ["root"]},
                {"id": "A", "handler": "input", "dependencies": ["B"]},
                {"id": "B", "handler": "output", "dependencies": ["C"]},
                {"id": "C", "handler": "output", "dependencies": ["A"]},
            ]
        },
    }

    errors = CycleDetectionRule().validate(workflow)

    assert len(errors) == 1
    assert errors[0].code == "cyclic_dependency"
    assert errors[0].meta["cycle_path"] == "A->B->C->A"


def test_cycle_detection_rule_rejects_graph_without_a_valid_starting_node() -> None:
    workflow = {
        "name": "no-root",
        "dag": {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": ["B"]},
                {"id": "B", "handler": "output", "dependencies": ["A"]},
            ]
        },
    }

    errors = CycleDetectionRule().validate(workflow)

    assert len(errors) == 1
    assert errors[0].code == "cyclic_dependency"
    assert errors[0].meta["cycle_path"] == "A->B->A"


def test_cycle_detection_rule_allows_large_acyclic_graph() -> None:
    node_count = 500
    nodes = [
        {
            "id": f"n{i}",
            "handler": "output" if i else "input",
            "dependencies": [] if i == 0 else [f"n{i - 1}"],
        }
        for i in range(node_count)
    ]
    workflow = {"name": "large-acyclic", "dag": {"nodes": nodes}}

    assert CycleDetectionRule().validate(workflow) == []


@pytest.mark.parametrize(
    "rule",
    [
        RequiredWorkflowFieldsRule(),
        RequiredNodeFieldsRule(),
        NodeIdValidityRule(),
        UniqueNodeIdsRule(),
        HandlerDefinitionRule(),
        NodeConfigurationRule(),
        DependencyReferenceRule(),
        CycleDetectionRule(),
    ],
)
def test_rules_accept_valid_fan_out_fan_in_workflow(
    rule: object, valid_workflow: dict[str, Any]
) -> None:
    assert rule.validate(valid_workflow) == []


def test_rules_do_not_mutate_workflow(valid_workflow: dict[str, Any]) -> None:
    workflow = valid_workflow
    original = deepcopy(workflow)

    for rule in (
        RequiredWorkflowFieldsRule(),
        RequiredNodeFieldsRule(),
        NodeIdValidityRule(),
        UniqueNodeIdsRule(),
        HandlerDefinitionRule(),
        NodeConfigurationRule(),
        DependencyReferenceRule(),
        CycleDetectionRule(),
    ):
        rule.validate(workflow)

    assert workflow == original
