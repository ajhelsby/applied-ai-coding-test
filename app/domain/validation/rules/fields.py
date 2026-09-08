"""Rules that validate required workflow and node properties."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation.rules._workflow import error


class RequiredWorkflowFieldsRule:
    """Require the workflow name and DAG node collection."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        errors: list[WorkflowValidationError] = []
        name = workflow.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(
                error(
                    "required_workflow_name",
                    "Workflow property 'name' must be a non-empty string.",
                    "name",
                )
            )

        dag = workflow.get("dag")
        if not isinstance(dag, Mapping):
            errors.append(
                error(
                    "required_workflow_dag",
                    "Workflow property 'dag' must be an object.",
                    "dag",
                )
            )
        elif not isinstance(dag.get("nodes"), list):
            errors.append(
                error(
                    "required_workflow_nodes",
                    "Workflow property 'dag.nodes' must be a list.",
                    "dag.nodes",
                )
            )
        return errors


class RequiredNodeFieldsRule:
    """Require each DAG node to define id, handler, and dependencies."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        errors: list[WorkflowValidationError] = []
        dag = workflow.get("dag")
        nodes = dag.get("nodes") if isinstance(dag, Mapping) else None
        if not isinstance(nodes, list):
            return errors

        for index, node in enumerate(nodes):
            path = f"dag.nodes[{index}]"
            if not isinstance(node, Mapping):
                errors.append(
                    error(
                        "invalid_node_definition",
                        "Workflow node must be an object.",
                        path,
                    )
                )
                continue

            node_id = node.get("id") if isinstance(node.get("id"), str) else None
            for field_name in ("id", "handler", "dependencies"):
                if field_name not in node:
                    errors.append(
                        error(
                            f"required_node_{field_name}",
                            f"Node property '{field_name}' is required.",
                            f"{path}.{field_name}",
                            node_id=node_id,
                        )
                    )
            if "dependencies" in node and not isinstance(node["dependencies"], list):
                errors.append(
                    error(
                        "invalid_node_dependencies",
                        "Node property 'dependencies' must be a list.",
                        f"{path}.dependencies",
                        node_id=node_id,
                    )
                )
        return errors
