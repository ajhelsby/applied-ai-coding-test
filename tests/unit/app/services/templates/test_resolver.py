from __future__ import annotations

import pytest

from app.domain.models.node import WorkflowNode
from app.domain.templates.parser import TemplateResolutionError
from app.services.templates.resolver import NodeInputResolver


def test_resolve_full_nested_reference() -> None:
    node = WorkflowNode(
        id="summarize",
        handler="example.handler",
        config={"user_name": "{{ get_user.profile.name }}"},
    )

    result = NodeInputResolver().resolve(
        node,
        execution_input={},
        dependency_outputs={"get_user": {"profile": {"name": "Ada"}}},
    )

    assert result == {"user_name": "Ada"}


def test_resolve_multiple_embedded_references() -> None:
    node = WorkflowNode(
        id="summarize",
        handler="example.handler",
        config={"summary": "{{ get_user.name }} has {{ get_user.id }}."},
    )

    result = NodeInputResolver().resolve(
        node,
        execution_input={},
        dependency_outputs={"get_user": {"name": "Ada", "id": 42}},
    )

    assert result == {"summary": "Ada has 42."}


def test_resolve_preserves_non_template_values() -> None:
    node = WorkflowNode(
        id="copy",
        handler="example.handler",
        config={"message": "unchanged", "count": 3, "enabled": True},
    )

    result = NodeInputResolver().resolve(
        node,
        execution_input={},
        dependency_outputs={},
    )

    assert result == {"message": "unchanged", "count": 3, "enabled": True}


def test_resolve_rejects_malformed_template_before_lookup() -> None:
    node = WorkflowNode(
        id="unsafe",
        handler="example.handler",
        config={"value": "{{ __import__('os').system('whoami') }}"},
    )

    with pytest.raises(TemplateResolutionError, match="Malformed template expression"):
        NodeInputResolver().resolve(
            node,
            execution_input={},
            dependency_outputs={},
        )
