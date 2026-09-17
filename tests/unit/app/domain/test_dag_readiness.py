"""Unit tests for pure dependency readiness evaluation."""

from __future__ import annotations

from typing import Any

from app.domain.dag import evaluate_failed_dependency_node_ids, evaluate_ready_node_ids
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
            "a": NodeExecutionStatus.RUNNING,
            "b": NodeExecutionStatus.RUNNING,
            "c": NodeExecutionStatus.COMPLETED,
            "d": NodeExecutionStatus.FAILED,
            "e": NodeExecutionStatus.FAILED,
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


def test_failed_dependency_propagates_through_multiple_levels() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "task", "dependencies": []},
            {"id": "b", "handler": "task", "dependencies": ["a"]},
            {"id": "c", "handler": "task", "dependencies": ["b"]},
            {"id": "d", "handler": "task", "dependencies": ["c"]},
        ]
    )

    skipped = evaluate_failed_dependency_node_ids(
        workflow,
        {"a": NodeExecutionStatus.FAILED},
    )

    assert skipped == ("b", "c", "d")


def test_failed_dependency_handles_fan_out_and_fan_in() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "task", "dependencies": []},
            {"id": "b", "handler": "task", "dependencies": ["a"]},
            {"id": "c", "handler": "task", "dependencies": ["a"]},
            {"id": "d", "handler": "task", "dependencies": ["b", "c"]},
        ]
    )

    skipped = evaluate_failed_dependency_node_ids(
        workflow,
        {"a": NodeExecutionStatus.FAILED},
    )

    assert skipped == ("b", "c", "d")


def test_failed_dependency_does_not_skip_independent_or_running_nodes() -> None:
    workflow = _workflow(
        [
            {"id": "failed", "handler": "task", "dependencies": []},
            {"id": "dependent", "handler": "task", "dependencies": ["failed"]},
            {"id": "independent", "handler": "task", "dependencies": []},
            {"id": "running", "handler": "task", "dependencies": ["failed"]},
        ]
    )

    skipped = evaluate_failed_dependency_node_ids(
        workflow,
        {
            "failed": NodeExecutionStatus.FAILED,
            "independent": NodeExecutionStatus.PENDING,
            "running": NodeExecutionStatus.RUNNING,
        },
    )

    assert skipped == ("dependent",)


def test_existing_skipped_dependency_continues_propagation() -> None:
    workflow = _workflow(
        [
            {"id": "a", "handler": "task", "dependencies": []},
            {"id": "b", "handler": "task", "dependencies": ["a"]},
            {"id": "c", "handler": "task", "dependencies": ["b"]},
        ]
    )

    skipped = evaluate_failed_dependency_node_ids(
        workflow,
        {"a": NodeExecutionStatus.FAILED, "b": NodeExecutionStatus.FAILED},
    )

    assert skipped == ("c",)
