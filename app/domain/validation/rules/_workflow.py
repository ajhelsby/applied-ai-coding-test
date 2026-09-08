"""Helpers for safely inspecting untrusted workflow definition payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError


def nodes_from(workflow: Mapping[str, Any]) -> list[tuple[int, Mapping[str, Any]]]:
    """Return mapping-shaped nodes only when dag.nodes is a list."""

    dag = workflow.get("dag")
    if not isinstance(dag, Mapping):
        return []

    nodes = dag.get("nodes")
    if not isinstance(nodes, list):
        return []

    return [(index, node) for index, node in enumerate(nodes) if isinstance(node, Mapping)]


def valid_node_ids(workflow: Mapping[str, Any]) -> set[str]:
    """Return non-empty string node identifiers."""

    return {
        node_id
        for _, node in nodes_from(workflow)
        if isinstance(node_id := node.get("id"), str) and node_id.strip()
    }


def error(
    code: str,
    message: str,
    path: str,
    *,
    node_id: str | None = None,
    dependency_id: str | None = None,
) -> WorkflowValidationError:
    """Create a validation error with standard contextual fields."""

    return WorkflowValidationError(
        code=code,
        message=message,
        path=path,
        node_id=node_id,
        dependency_id=dependency_id,
    )
