"""Shared validation helpers for flat Redis stream fields."""

from __future__ import annotations

from collections.abc import Mapping
from json import JSONDecodeError, loads
from typing import TypeGuard

from app.domain.models.json import JsonValue


def required_field(fields: Mapping[str, str], field_name: str, message_type: str) -> str:
    """Return a required non-empty stream field."""

    value = fields.get(field_name)
    if value is None or not value.strip():
        raise ValueError(f"{message_type} field '{field_name}' is required.")
    return value


def json_value_field(
    fields: Mapping[str, str],
    field_name: str,
    message_type: str,
) -> JsonValue:
    """Parse a required JSON-value stream field."""

    serialized_value = required_field(fields, field_name, message_type)
    try:
        value: object = loads(serialized_value)
    except JSONDecodeError as error:
        raise ValueError(f"{message_type} field '{field_name}' must contain JSON.") from error
    if not is_json_value(value):
        raise ValueError(f"{message_type} field '{field_name}' must contain valid JSON.")
    return value


def json_object_field(
    fields: Mapping[str, str],
    field_name: str,
    message_type: str,
) -> dict[str, JsonValue]:
    """Parse a required JSON-object stream field."""

    value = json_value_field(fields, field_name, message_type)
    if not isinstance(value, dict):
        raise ValueError(f"{message_type} field '{field_name}' must contain a JSON object.")
    return value


def is_json_value(value: object) -> TypeGuard[JsonValue]:
    """Return whether a value contains only JSON-compatible values."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_value(item) for key, item in value.items())
    return False
