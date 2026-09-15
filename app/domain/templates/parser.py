"""Parse workflow output references without resolving their values."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TEMPLATE_DELIMITER_PATTERN = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_PATH_SEGMENT_PATTERN = r"(?:[A-Za-z][A-Za-z0-9_-]*|[0-9]+)"
_REFERENCE_EXPRESSION_PATTERN = re.compile(
    r"\s*(?P<node_id>[A-Za-z][A-Za-z0-9_-]*)"
    rf"(?:\s*\.\s*(?P<path>{_PATH_SEGMENT_PATTERN}"
    rf"(?:\s*\.\s*{_PATH_SEGMENT_PATTERN})*))\s*"
)


@dataclass(frozen=True, slots=True)
class TemplateReference:
    """A reference to an output path from a completed workflow node."""

    node_id: str
    path: tuple[str, ...]


TemplateSegment = str | TemplateReference
ParsedTemplateString = tuple[TemplateSegment, ...]


class TemplateResolutionError(ValueError):
    """Raised when a task input template cannot be resolved safely."""


class TemplateParser:
    """Parse safe workflow output references without resolving their values."""

    def parse(self, value: str) -> str | TemplateReference | ParsedTemplateString:
        """Parse a string into literal text and output reference segments."""

        if "{{" not in value and "}}" not in value:
            return value

        matches = list(_TEMPLATE_DELIMITER_PATTERN.finditer(value))
        self._validate_delimiters(value, matches)
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return self._parse_reference(matches[0].group(0))

        segments: list[TemplateSegment] = []
        cursor = 0
        for match in matches:
            if match.start() > cursor:
                segments.append(value[cursor : match.start()])
            segments.append(self._parse_reference(match.group(0)))
            cursor = match.end()
        if cursor < len(value):
            segments.append(value[cursor:])
        return tuple(segments)

    @staticmethod
    def _validate_delimiters(value: str, matches: list[re.Match[str]]) -> None:
        covered: list[tuple[int, int]] = [match.span() for match in matches]
        for delimiter in ("{{", "}}"):
            position = value.find(delimiter)
            while position >= 0:
                if not any(start <= position < end for start, end in covered):
                    raise TemplateResolutionError(
                        f"Malformed template expression: unmatched '{delimiter}'."
                    )
                position = value.find(delimiter, position + len(delimiter))

    @staticmethod
    def _parse_reference(template: str) -> TemplateReference:
        expression = template[2:-2]
        match = _REFERENCE_EXPRESSION_PATTERN.fullmatch(expression)
        if match is None:
            raise TemplateResolutionError(
                f"Malformed template expression {template!r}; expected "
                "'{{ node_name.output.path }}'."
            )

        path = tuple(part.strip() for part in match["path"].split("."))
        return TemplateReference(node_id=match["node_id"], path=path)
