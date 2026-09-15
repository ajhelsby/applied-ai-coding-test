"""JSON-compatible domain value types."""

from __future__ import annotations

from typing import TypeAlias

JsonValue: TypeAlias = (  # noqa: UP040
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
