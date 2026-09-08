"""Unit tests for pure dependency readiness evaluation."""

from __future__ import annotations

from typing import Any

from app.domain.dag import evaluate_ready_node_ids
from app.domain.models.workflow import Workflow
from app.domain.state.states import NodeExecutionStatus


def _workflow(nodes: list[dict[str, Any]]) -> Workflow:
    return Workflow.model_validate({"name": "test-workflow", "dag": {"nodes": nodes}})


def test_root_nodes_with_no_dependencies_are_ready() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "task", "dependencies": []},
            {"id": "b", "handler": "task", "dependencies": []},
        ]
    )

    ready = evaluate_ready_node_ids(workflow, {})

    assert ready == ("a", "b")


def test_linear_node_becomes_ready_only_after_parent_completed() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "task", "dependencies": []},
            {"id": "b", "handler": "task", "dependencies": ["a"]},
        ]
    )

    assert evaluate_ready_node_ids(workflow, {"a": NodeExecutionStatus.PENDING}) == ("a",)
    assert evaluate_ready_node_ids(workflow, {"a": NodeExecutionStatus.COMPLETED}) == ("b",)


def test_fan_out_makes_multiple_downstream_nodes_ready_together() -> None:
    workflow = _workflow(
        [
            {"id": "root", "handler": "task", "dependencies": []},
            {"id": "left", "handler": "task", "dependencies": ["root"]},
            {"id": "right", "handler": "task", "dependencies": ["root"]},
        ]
    )

    ready = evaluate_ready_node_ids(workflow, {"root": NodeExecutionStatus.COMPLETED})

    assert ready == ("left", "right")


def test_fan_in_waits_until_all_parents_completed() -> None:
    workflow = _workflow(
        [
            {"id": "left", "handler": "task", "dependencies": []},
            {"id": "right", "handler": "task", "dependencies": []},
            {"id": "join", "handler": "task", "dependencies": ["left", "right"]},
        ]
    )

    assert evaluate_ready_node_ids(
        workflow,
        {"left": NodeExecutionStatus.COMPLETED, "right": NodeExecutionStatus.PENDING},
    ) == ("right",)
    assert evaluate_ready_node_ids(
        workflow,
        {"left": NodeExecutionStatus.COMPLETED, "right": NodeExecutionStatus.COMPLETED},
    ) == ("join",)


def test_failed_or_incomplete_dependencies_block_readiness() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "task", "dependencies": []},
            {"id": "b", "handler": "task", "dependencies": ["a"]},
        ]
    )

    assert evaluate_ready_node_ids(workflow, {"a": NodeExecutionStatus.FAILED}) == ()
    assert evaluate_ready_node_ids(workflow, {"a": NodeExecutionStatus.RUNNING}) == ()


def test_already_processed_or_running_nodes_are_not_returned() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "task", "dependencies": []},
            {"id": "b", "handler": "task", "dependencies": []},
            {"id": "c", "handler": "task", "dependencies": []},
            {"id": "d", "handler": "task", "dependencies": []},
            {"id": "e", "handler": "task", "dependencies": []},
        ]
    )

    ready = evaluate_ready_node_ids(
        workflow,
        {
            "a": NodeExecutionStatus.READY,
            "b": NodeExecutionStatus.RUNNING,
            "c": NodeExecutionStatus.COMPLETED,
            "d": NodeExecutionStatus.FAILED,
            "e": NodeExecutionStatus.SKIPPED,
        },
    )

    assert ready == ()


def test_repeated_evaluation_is_deterministic_for_same_state() -> None:
    workflow = _workflow(
        [
            {"id": "root", "handler": "task", "dependencies": []},
            {"id": "left", "handler": "task", "dependencies": ["root"]},
            {"id": "right", "handler": "task", "dependencies": ["root"]},
        ]
    )
    statuses = {"root": NodeExecutionStatus.COMPLETED}

    first = evaluate_ready_node_ids(workflow, statuses)
    second = evaluate_ready_node_ids(workflow, statuses)

    assert first == ("left", "right")
    assert second == ("left", "right")
