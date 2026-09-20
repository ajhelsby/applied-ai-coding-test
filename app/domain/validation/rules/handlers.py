"""Rules for allowed node handlers and their configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from app.domain.errors.validation import WorkflowValidationError
from app.domain.validation.rules._workflow import error, nodes_from

ALLOWED_HANDLERS = frozenset({"input", "output", "call_external_service", "llm_service"})
INTEGRATION_HANDLER = "integration_barrier"


class HandlerDefinitionRule:
    """Require a handler from the supported handler set."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        errors: list[WorkflowValidationError] = []
        allowed_handlers = ALLOWED_HANDLERS
        if os.getenv("INTEGRATION_TEST") == "1":
            allowed_handlers = allowed_handlers | {INTEGRATION_HANDLER}
        for index, node in nodes_from(workflow):
            handler = node.get("handler")
            if not isinstance(handler, str) or handler not in allowed_handlers:
                node_id = node.get("id")
                errors.append(
                    error(
                        "invalid_handler",
                        "Node property 'handler' must be one of: "
                        + ", ".join(sorted(allowed_handlers))
                        + ".",
                        f"dag.nodes[{index}].handler",
                        node_id=node_id if isinstance(node_id, str) else None,
                    )
                )
        return errors


class NodeConfigurationRule:
    """Validate configuration required by supported handlers."""

    def validate(self, workflow: Mapping[str, Any]) -> list[WorkflowValidationError]:
        errors: list[WorkflowValidationError] = []
        for index, node in nodes_from(workflow):
            handler = node.get("handler")
            node_id = node.get("id")
            context = node_id if isinstance(node_id, str) else None
            config = node.get("config", {})
            path = f"dag.nodes[{index}].config"

            if handler == "call_external_service":
                if (
                    not isinstance(config, Mapping)
                    or not isinstance(config.get("url"), str)
                    or not config["url"].strip()
                ):
                    errors.append(
                        error(
                            "invalid_handler_config",
                            "Handler 'call_external_service' requires a non-empty "
                            "string 'config.url'.",
                            f"{path}.url",
                            node_id=context,
                        )
                    )
            elif handler == "llm_service":
                if (
                    not isinstance(config, Mapping)
                    or not isinstance(config.get("prompt"), str)
                    or not config["prompt"].strip()
                ):
                    errors.append(
                        error(
                            "invalid_handler_config",
                            "Handler 'llm_service' requires a non-empty string 'config.prompt'.",
                            f"{path}.prompt",
                            node_id=context,
                        )
                    )
            elif handler in {"input", "output"} and config:
                errors.append(
                    error(
                        "invalid_handler_config",
                        f"Handler '{handler}' does not accept configuration.",
                        path,
                        node_id=context,
                    )
                )
        return errors
