"""Rules for node dependency references."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation.rules._workflow import error, nodes_from, valid_node_ids


class DependencyReferencesRule:
    """Reject dependencies that do not reference a declared node."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        known_ids = valid_node_ids(workflow)
        errors: list[WorkflowValidationError] = []
        for index, node in nodes_from(workflow):
            dependencies = node.get("dependencies")
            if not isinstance(dependencies, list):
                continue
            node_id = node.get("id")
            context = node_id if isinstance(node_id, str) else None
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
        return errors


class SelfDependencyRule:
    """Reject nodes that depend on themselves."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        errors: list[WorkflowValidationError] = []
        for index, node in nodes_from(workflow):
            node_id = node.get("id")
            dependencies = node.get("dependencies")
            if not isinstance(node_id, str) or not isinstance(dependencies, list):
                continue
            for dependency_index, dependency_id in enumerate(dependencies):
                if dependency_id == node_id:
                    errors.append(
                        error(
                            "self_dependency",
                            f"Node '{node_id}' cannot depend on itself.",
                            f"dag.nodes[{index}].dependencies[{dependency_index}]",
                            node_id=node_id,
                            dependency_id=node_id,
                        )
                    )
        return errors
