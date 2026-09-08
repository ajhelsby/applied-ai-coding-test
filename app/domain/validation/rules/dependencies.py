"""Rules for node dependency references."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation.rules._workflow import error, nodes_from, valid_node_ids


class DependencyReferenceRule:
    """Reject unknown, self, and duplicate node dependency references."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        known_ids = valid_node_ids(workflow)
        errors: list[WorkflowValidationError] = []
        for index, node in nodes_from(workflow):
            dependencies = node.get("dependencies")
            if not isinstance(dependencies, list):
                continue
            node_id = node.get("id")
            context = node_id if isinstance(node_id, str) else None
            seen: set[str] = set()
            for dependency_index, dependency_id in enumerate(dependencies):
                if not isinstance(dependency_id, str) or dependency_id not in known_ids:
                    errors.append(
                        error(
                            "unknown_dependency",
                            f"Node '{context or index}' references unknown dependency "
                            f"'{dependency_id}'.",
                            f"dag.nodes[{index}].dependencies[{dependency_index}]",
                            node_id=context,
                            dependency_id=(
                                dependency_id if isinstance(dependency_id, str) else None
                            ),
                        )
                    )
                    continue

                if context is not None and dependency_id == context:
                    errors.append(
                        error(
                            "self_dependency",
                            f"Node '{context}' cannot depend on itself.",
                            f"dag.nodes[{index}].dependencies[{dependency_index}]",
                            node_id=context,
                            dependency_id=dependency_id,
                        )
                    )
                    continue

                if dependency_id in seen:
                    errors.append(
                        error(
                            "duplicate_dependency",
                            f"Node '{context or index}' declares duplicate dependency "
                            f"'{dependency_id}'.",
                            f"dag.nodes[{index}].dependencies[{dependency_index}]",
                            node_id=context,
                            dependency_id=dependency_id,
                        )
                    )
                    continue

                seen.add(dependency_id)
        return errors
