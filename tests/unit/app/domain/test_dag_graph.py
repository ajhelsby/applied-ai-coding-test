"""Unit tests for internal DAG graph representation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.dag import DAG
from app.domain.models.workflow import Workflow


def _workflow(nodes: list[dict[str, Any]]) -> Workflow:
    return Workflow.model_validate({"name": "test-workflow", "dag": {"nodes": nodes}})


def test_dag_from_workflow_supports_linear_traversal() -> None:
    workflow = _workflow(
        [
            {"id": "n1", "handler": "input", "dependencies": []},
            {"id": "n2", "handler": "output", "dependencies": ["n1"]},
            {"id": "n3", "handler": "output", "dependencies": ["n2"]},
        ]
    )

    dag = DAG.from_workflow(workflow)

    assert tuple(node.node_id for node in dag.get_roots()) == ("n1",)
    assert tuple(node.node_id for node in dag.get_terminals()) == ("n3",)
    assert tuple(node.node_id for node in dag.get_dependencies("n3")) == ("n2",)
    assert tuple(node.node_id for node in dag.get_dependants("n1")) == ("n2",)


def test_dag_from_workflow_supports_branching_traversal() -> None:
    workflow = _workflow(
        [
            {"id": "root", "handler": "input", "dependencies": []},
            {"id": "left", "handler": "output", "dependencies": ["root"]},
            {"id": "right", "handler": "output", "dependencies": ["root"]},
        ]
    )

    dag = DAG.from_workflow(workflow)

    assert tuple(node.node_id for node in dag.get_roots()) == ("root",)
    assert {node.node_id for node in dag.get_terminals()} == {"left", "right"}
    assert tuple(node.node_id for node in dag.get_dependencies("left")) == ("root",)
    assert tuple(node.node_id for node in dag.get_dependants("root")) == ("left", "right")


def test_dag_from_workflow_supports_fan_in_fan_out_traversal() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "input", "dependencies": []},
            {"id": "b", "handler": "output", "dependencies": ["a"]},
            {"id": "c", "handler": "output", "dependencies": ["a"]},
            {"id": "d", "handler": "output", "dependencies": ["b", "c"]},
            {"id": "e", "handler": "output", "dependencies": ["d"]},
            {"id": "f", "handler": "output", "dependencies": ["d"]},
        ]
    )

    dag = DAG.from_workflow(workflow)

    assert tuple(node.node_id for node in dag.get_roots()) == ("a",)
    assert {node.node_id for node in dag.get_terminals()} == {"e", "f"}
    assert tuple(node.node_id for node in dag.get_dependencies("d")) == ("b", "c")
    assert tuple(node.node_id for node in dag.get_dependants("d")) == ("e", "f")


def test_dag_from_workflow_supports_multi_root_graphs() -> None:
    workflow = _workflow(
        [
            {"id": "r1", "handler": "input", "dependencies": []},
            {"id": "r2", "handler": "input", "dependencies": []},
            {"id": "join", "handler": "output", "dependencies": ["r1", "r2"]},
        ]
    )

    dag = DAG.from_workflow(workflow)

    assert {node.node_id for node in dag.get_roots()} == {"r1", "r2"}
    assert tuple(node.node_id for node in dag.get_terminals()) == ("join",)
    assert tuple(node.node_id for node in dag.get_dependencies("join")) == ("r1", "r2")


def test_dag_from_workflow_preserves_config_and_does_not_mutate_original() -> None:
    definition = {
        "name": "config-workflow",
        "dag": {
            "nodes": [
                {
                    "id": "fetch",
                    "handler": "call_external_service",
                    "dependencies": [],
                    "config": {"url": "https://example.test/api"},
                }
            ]
        },
    }
    original = deepcopy(definition)
    workflow = Workflow.model_validate(definition)

    dag = DAG.from_workflow(workflow)
    fetch = dag.get_node("fetch")

    assert dict(fetch.config) == {"url": "https://example.test/api"}
    assert definition == original
