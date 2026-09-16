"""Unit tests for internal DAG graph representation."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.domain.dag import DAG
from app.domain.models.workflow import Workflow


def test_dag_from_workflow_supports_linear_traversal(
    workflow_from_nodes: Callable[[list[dict[str, Any]]], Workflow],
) -> None:
    workflow = workflow_from_nodes(
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


def test_dag_from_workflow_supports_branching_traversal(
    workflow_from_nodes: Callable[[list[dict[str, Any]]], Workflow],
) -> None:
    workflow = workflow_from_nodes(
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


def test_dag_from_workflow_supports_fan_in_fan_out_traversal(
    workflow_from_nodes: Callable[[list[dict[str, Any]]], Workflow],
) -> None:
    workflow = workflow_from_nodes(
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


def test_dag_from_workflow_supports_multi_root_graphs(
    workflow_from_nodes: Callable[[list[dict[str, Any]]], Workflow],
) -> None:
    workflow = workflow_from_nodes(
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


def test_dag_from_workflow_represents_all_nodes_and_adjacency(
    workflow_from_nodes: Callable[[list[dict[str, Any]]], Workflow],
) -> None:
    workflow = workflow_from_nodes(
        [
            {"id": "root", "handler": "input", "dependencies": []},
            {"id": "left", "handler": "output", "dependencies": ["root"]},
            {"id": "right", "handler": "output", "dependencies": ["root"]},
            {"id": "join", "handler": "output", "dependencies": ["left", "right"]},
        ]
    )

    dag = DAG.from_workflow(workflow)

    assert {dag.get_node(node_id).node_id for node_id in ("root", "left", "right", "join")} == {
        "root",
        "left",
        "right",
        "join",
    }
    assert tuple(node.node_id for node in dag.get_dependencies("join")) == ("left", "right")
    assert tuple(node.node_id for node in dag.get_dependants("root")) == ("left", "right")
    assert tuple(node.node_id for node in dag.get_dependants("left")) == ("join",)
    assert tuple(node.node_id for node in dag.get_dependants("right")) == ("join",)
    assert tuple(node.node_id for node in dag.get_roots()) == ("root",)
    assert tuple(node.node_id for node in dag.get_terminals()) == ("join",)


def test_dag_from_workflow_traverses_disconnected_components(
    workflow_from_nodes: Callable[[list[dict[str, Any]]], Workflow],
) -> None:
    workflow = workflow_from_nodes(
        [
            {"id": "a-root", "handler": "input", "dependencies": []},
            {"id": "a-child", "handler": "output", "dependencies": ["a-root"]},
            {"id": "b-root", "handler": "input", "dependencies": []},
            {"id": "b-child", "handler": "output", "dependencies": ["b-root"]},
        ]
    )

    dag = DAG.from_workflow(workflow)
    discovered: set[str] = set()
    pending = list(dag.get_roots())

    while pending:
        node = pending.pop()
        if node.node_id in discovered:
            continue
        discovered.add(node.node_id)
        pending.extend(dag.get_dependants(node.node_id))

    assert discovered == {"a-root", "a-child", "b-root", "b-child"}
    assert {node.node_id for node in dag.get_roots()} == {"a-root", "b-root"}
    assert {node.node_id for node in dag.get_terminals()} == {"a-child", "b-child"}


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
