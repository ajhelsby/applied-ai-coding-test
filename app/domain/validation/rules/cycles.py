"""Rule for detecting cycles in workflow dependencies."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation.rules._workflow import nodes_from
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
        stack_index: dict[str, int] = {}
        traversal_stack: list[str] = []
        errors: list[WorkflowValidationError] = []
        seen_cycle_paths: set[tuple[str, ...]] = set()

        for start_node_id in graph:
            if start_node_id in visited:
                continue

            frame_stack: list[tuple[str, int]] = [(start_node_id, 0)]
            visited.add(start_node_id)
            active.add(start_node_id)
            stack_index[start_node_id] = 0
            traversal_stack.append(start_node_id)

            while frame_stack:
                node_id, dependency_index = frame_stack[-1]
                dependencies = graph[node_id]

                if dependency_index >= len(dependencies):
                    frame_stack.pop()
                    active.remove(node_id)
                    stack_index.pop(node_id, None)
                    traversal_stack.pop()
                    continue

                dependency_id = dependencies[dependency_index]
                frame_stack[-1] = (node_id, dependency_index + 1)

                if dependency_id in active:
                    cycle_start_index = stack_index[dependency_id]
                    cycle_path = traversal_stack[cycle_start_index:] + [dependency_id]
                    cycle_key = tuple(cycle_path)
                    if cycle_key in seen_cycle_paths:
                        continue
                    seen_cycle_paths.add(cycle_key)
                    errors.append(
                        WorkflowValidationError(
                            code="cyclic_dependency",
                            message=(
                                f"Node '{node_id}' participates in a cyclic dependency "
                                f"through '{dependency_id}'."
                            ),
                            path="dag.nodes",
                            node_id=node_id,
                            dependency_id=dependency_id,
                            meta={"cycle_path": "->".join(cycle_path)},
                        )
                    )
                    continue

                if dependency_id not in graph or dependency_id in visited:
                    continue

                visited.add(dependency_id)
                active.add(dependency_id)
                stack_index[dependency_id] = len(traversal_stack)
                traversal_stack.append(dependency_id)
                frame_stack.append((dependency_id, 0))
        return errors
