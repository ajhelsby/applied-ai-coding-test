"""Rule for detecting cycles in workflow dependencies."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation.rules._workflow import error, nodes_from
from app.domain.validation.rules.node_ids import NODE_ID_PATTERN


class CycleDetectionRule:
    """Detect directed dependency cycles among uniquely identified nodes."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        nodes = nodes_from(workflow)
        identifiers = [
            node_id
            for _, node in nodes
            if isinstance(node_id := node.get("id"), str) and NODE_ID_PATTERN.fullmatch(node_id)
        ]
        counts = Counter(identifiers)
        graph = {
            node_id: [
                dependency_id
                for dependency_id in node.get("dependencies", [])
                if isinstance(dependency_id, str)
                and dependency_id != node_id
                and counts[dependency_id] == 1
            ]
            for _, node in nodes
            if isinstance(node_id := node.get("id"), str) and counts[node_id] == 1
        }
        visited: set[str] = set()
        active: set[str] = set()
        errors: list[WorkflowValidationError] = []

        def visit(node_id: str) -> None:
            visited.add(node_id)
            active.add(node_id)
            for dependency_id in graph[node_id]:
                if dependency_id in active:
                    errors.append(
                        error(
                            "cyclic_dependency",
                            f"Node '{node_id}' participates in a cyclic dependency "
                            f"through '{dependency_id}'.",
                            "dag.nodes",
                            node_id=node_id,
                            dependency_id=dependency_id,
                        )
                    )
                elif dependency_id in graph and dependency_id not in visited:
                    visit(dependency_id)
            active.remove(node_id)

        for node_id in graph:
            if node_id not in visited:
                visit(node_id)
        return errors
