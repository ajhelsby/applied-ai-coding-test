"""Resolve workflow node input templates from completed dependency outputs."""

from __future__ import annotations

import math
from collections.abc import Mapping

from app.domain.models.json import JsonValue
from app.domain.models.node import WorkflowNode
from app.domain.templates.parser import (
    ParsedTemplateString,
    TemplateParser,
    TemplateReference,
    TemplateResolutionError,
)


class NodeInputResolver:
    """Build JSON-safe worker input from node configuration and completed outputs."""

    def __init__(self, parser: TemplateParser | None = None) -> None:
        self._parser = parser or TemplateParser()

    def resolve(
        self,
        node: WorkflowNode,
        execution_input: Mapping[str, object],
        dependency_outputs: Mapping[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Resolve a node's worker input without performing I/O or dependency traversal."""

        if node.handler == "input":
            return self._copy_object(execution_input)
        if node.handler == "output":
            return self._copy_object(dependency_outputs)

        return self._resolve_object(node.config, dependency_outputs)

    def _resolve_object(
        self,
        value: Mapping[str, object],
        dependency_outputs: Mapping[str, JsonValue],
    ) -> dict[str, JsonValue]:
        return {key: self._resolve_value(item, dependency_outputs) for key, item in value.items()}

    def _resolve_value(
        self,
        value: object,
        dependency_outputs: Mapping[str, JsonValue],
    ) -> JsonValue:
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
        dependency_outputs: Mapping[str, JsonValue],
    ) -> JsonValue:
        parsed = self._parser.parse(value)
        if isinstance(parsed, str):
            return parsed
        if isinstance(parsed, TemplateReference):
            return self._copy_json_value(self._lookup(parsed, dependency_outputs))
        return self._interpolate_segments(parsed, dependency_outputs)

    def _lookup(
        self,
        reference: TemplateReference,
        dependency_outputs: Mapping[str, JsonValue],
    ) -> JsonValue:
        node_id = reference.node_id
        try:
            current: JsonValue = dependency_outputs[node_id]
        except KeyError as error:
            raise TemplateResolutionError(
                f"Template references unavailable dependency output '{node_id}'."
            ) from error

        reference_path = f"{node_id}.{'.'.join(reference.path)}"
        for key in reference.path:
            if isinstance(current, Mapping):
                if key not in current:
                    raise TemplateResolutionError(
                        f"Template references missing output '{reference_path}'."
                    )
                current = current[key]
                continue

            if isinstance(current, list):
                if not key.isdecimal() or int(key) >= len(current):
                    raise TemplateResolutionError(
                        f"Template references missing output '{reference_path}'."
                    )
                current = current[int(key)]
                continue

            raise TemplateResolutionError(f"Template references missing output '{reference_path}'.")
        return current

    def _interpolate_segments(
        self,
        segments: ParsedTemplateString,
        dependency_outputs: Mapping[str, JsonValue],
    ) -> str:
        return "".join(
            segment if isinstance(segment, str) else self._interpolate(segment, dependency_outputs)
            for segment in segments
        )

    def _interpolate(
        self,
        reference: TemplateReference,
        dependency_outputs: Mapping[str, JsonValue],
    ) -> str:
        resolved = self._lookup(reference, dependency_outputs)
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
            f"'{reference.node_id}.{'.'.join(reference.path)}' resolved to a structured value."
        )

    @classmethod
    def _copy_object(cls, value: Mapping[str, object]) -> dict[str, JsonValue]:
        return {key: cls._copy_json_value(item) for key, item in value.items()}

    @classmethod
    def _copy_json_value(cls, value: object) -> JsonValue:
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
