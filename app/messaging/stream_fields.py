"""Shared validation helpers for flat Redis stream fields."""

from __future__ import annotations

from collections.abc import Mapping
from json import JSONDecodeError, loads


def required_field(fields: Mapping[str, str], field_name: str, message_type: str) -> str:
    """Return a required non-empty stream field."""

    value = fields.get(field_name)
    if value is None or not value.strip():
        raise ValueError(f"{message_type} field '{field_name}' is required.")
    return value


def json_object_field(
    fields: Mapping[str, str],
    field_name: str,
    message_type: str,
) -> dict[str, object]:
    """Parse a required JSON-object stream field."""

    serialized_value = required_field(fields, field_name, message_type)
    try:
        value = loads(serialized_value)
    except JSONDecodeError as error:
        raise ValueError(f"{message_type} field '{field_name}' must contain JSON.") from error
    if not isinstance(value, dict):
        raise ValueError(f"{message_type} field '{field_name}' must contain a JSON object.")
    return value
