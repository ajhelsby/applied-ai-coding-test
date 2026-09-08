"""Rules that validate workflow node identifiers."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation.rules._workflow import error, nodes_from

NODE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class NodeIdValidityRule:
    """Require node IDs to be non-empty identifier strings."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        errors: list[WorkflowValidationError] = []
        for index, node in nodes_from(workflow):
            node_id = node.get("id")
            if not isinstance(node_id, str) or not NODE_ID_PATTERN.fullmatch(node_id):
                errors.append(
                    error(
                        "invalid_node_id",
                        "Node property 'id' must start with a letter and contain only "
                        "letters, numbers, underscores, or hyphens.",
                        f"dag.nodes[{index}].id",
                        node_id=node_id if isinstance(node_id, str) else None,
                    )
                )
        return errors


class UniqueNodeIdsRule:
    """Reject duplicate valid node IDs."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        nodes = nodes_from(workflow)
        counts = Counter(
            node_id
            for _, node in nodes
            if isinstance(node_id := node.get("id"), str) and NODE_ID_PATTERN.fullmatch(node_id)
        )
        return [
            error(
                "duplicate_node_id",
                f"Node ID '{node_id}' is defined more than once.",
                f"dag.nodes[{index}].id",
                node_id=node_id,
            )
            for index, node in nodes
            if isinstance(node_id := node.get("id"), str) and counts[node_id] > 1
        ]
