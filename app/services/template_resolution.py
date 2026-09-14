"""Resolve workflow node input templates from completed dependency outputs."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from app.domain.models.node import WorkflowNode

_TEMPLATE_PATTERN = re.compile(
    r"\{\{\s*(?P<node_id>[A-Za-z][A-Za-z0-9_-]*)\."
    r"(?P<path>[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*)\s*\}\}"
)


class TemplateResolutionError(ValueError):
    """Raised when a task input template cannot be resolved safely."""


class NodeInputResolver:
    """Build JSON-safe worker input from node configuration and completed outputs."""

    def resolve(
        self,
        node: WorkflowNode,
        execution_input: Mapping[str, object],
        dependency_outputs: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        """Resolve a node's worker input without performing I/O or dependency traversal."""

        if node.handler == "input":
            return self._copy_object(execution_input)
        if node.handler == "output":
            return self._copy_object(dependency_outputs)

        return self._resolve_object(node.config, dependency_outputs)

    def _resolve_object(
        self,
        value: Mapping[str, object],
        dependency_outputs: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        return {
            key: self._resolve_value(item, dependency_outputs)
            for key, item in value.items()
        }

    def _resolve_value(
        self,
        value: object,
        dependency_outputs: Mapping[str, Mapping[str, object]],
    ) -> object:
        if isinstance(value, str):
            return self._resolve_string(value, dependency_outputs)
        if isinstance(value, list):
            return [self._resolve_value(item, dependency_outputs) for item in value]
        if isinstance(value, Mapping):
            return self._resolve_object(self._string_keyed_mapping(value), dependency_outputs)
        return self._copy_json_value(value)

    def _resolve_string(
        self,
        value: str,
        dependency_outputs: Mapping[str, Mapping[str, object]],
    ) -> object:
        full_match = _TEMPLATE_PATTERN.fullmatch(value)
        if full_match is not None:
            return self._copy_json_value(self._lookup(full_match, dependency_outputs))

        return _TEMPLATE_PATTERN.sub(
            lambda match: self._interpolate(match, dependency_outputs),
            value,
        )

    def _lookup(
        self,
        match: re.Match[str],
        dependency_outputs: Mapping[str, Mapping[str, object]],
    ) -> object:
        node_id = match["node_id"]
        try:
            current: object = dependency_outputs[node_id]
        except KeyError as error:
            raise TemplateResolutionError(
                f"Template references unavailable dependency output '{node_id}'."
            ) from error

        for key in match["path"].split("."):
            if not isinstance(current, Mapping) or key not in current:
                raise TemplateResolutionError(
                    f"Template references missing output '{node_id}.{match['path']}'."
                )
            current = current[key]
        return current

    def _interpolate(
        self,
        match: re.Match[str],
        dependency_outputs: Mapping[str, Mapping[str, object]],
    ) -> str:
        resolved = self._lookup(match, dependency_outputs)
        if isinstance(resolved, str):
            return resolved
        if resolved is None:
            return "null"
        if isinstance(resolved, bool):
            return "true" if resolved else "false"
        if isinstance(resolved, int | float):
            return str(resolved)
        raise TemplateResolutionError(
            "Embedded templates must resolve to scalar JSON values; "
            f"'{match.group(0)}' resolved to a structured value."
        )

    @classmethod
    def _copy_object(cls, value: Mapping[str, object]) -> dict[str, object]:
        return {key: cls._copy_json_value(item) for key, item in value.items()}

    @classmethod
    def _copy_json_value(cls, value: object) -> object:
        if value is None or isinstance(value, bool | int | str):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise TemplateResolutionError("Task input must contain only finite JSON numbers.")
            return value
        if isinstance(value, list):
            return [cls._copy_json_value(item) for item in value]
        if isinstance(value, Mapping):
            return cls._copy_object(cls._string_keyed_mapping(value))
        raise TemplateResolutionError(
            f"Task input contains non-JSON-serializable value of type '{type(value).__name__}'."
        )

    @staticmethod
    def _string_keyed_mapping(value: Mapping[object, object]) -> Mapping[str, object]:
        if not all(isinstance(key, str) for key in value):
            raise TemplateResolutionError("Task input objects must use string keys.")
        return {key: item for key, item in value.items() if isinstance(key, str)}
