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


def test_resolve_reference_through_nested_objects_and_arrays() -> None:
    node = WorkflowNode(
        id="summarize",
        handler="example.handler",
        config={
            "user_name": "{{ get_users.0.profile.name }}",
            "second_user_id": "{{ get_users.1.id }}",
        },
    )

    result = NodeInputResolver().resolve(
        node,
        execution_input={},
        dependency_outputs={
            "get_users": [
                {"profile": {"name": "Ada"}, "id": 1},
                {"profile": {"name": "Grace"}, "id": 2},
            ]
        },
    )

    assert result == {"user_name": "Ada", "second_user_id": 2}


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


def test_resolve_standalone_reference_preserves_json_type() -> None:
    node = WorkflowNode(
        id="copy",
        handler="example.handler",
        config={
            "number": "{{ get_user.id }}",
            "enabled": "{{ get_user.enabled }}",
            "profile": "{{ get_user.profile }}",
            "tags": "{{ get_user.tags }}",
        },
    )

    result = NodeInputResolver().resolve(
        node,
        execution_input={},
        dependency_outputs={
            "get_user": {
                "id": 123,
                "enabled": True,
                "profile": {"name": "Ada"},
                "tags": ["admin", "active"],
            }
        },
    )

    assert result == {
        "number": 123,
        "enabled": True,
        "profile": {"name": "Ada"},
        "tags": ["admin", "active"],
    }


def test_resolve_templates_recursively_in_nested_objects_and_arrays() -> None:
    node = WorkflowNode(
        id="copy",
        handler="example.handler",
        config={
            "users": [
                {"name": "{{ get_user.name }}"},
                ["{{ get_user.id }}", "User: {{ get_user.name }}"],
            ]
        },
    )

    result = NodeInputResolver().resolve(
        node,
        execution_input={},
        dependency_outputs={"get_user": {"id": 123, "name": "Ada"}},
    )

    assert result == {
        "users": [
            {"name": "Ada"},
            [123, "User: Ada"],
        ]
    }


def test_resolve_embedded_templates_converts_scalar_values() -> None:
    node = WorkflowNode(
        id="copy",
        handler="example.handler",
        config={
            "summary": "id={{ get_user.id }}, enabled={{ get_user.enabled }}, "
            "missing={{ get_user.nickname }}",
        },
    )

    result = NodeInputResolver().resolve(
        node,
        execution_input={},
        dependency_outputs={
            "get_user": {"id": 123, "enabled": False, "nickname": None},
        },
    )

    assert result == {"summary": "id=123, enabled=false, missing=null"}


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


def test_resolve_rejects_missing_dependency_output() -> None:
    node = WorkflowNode(
        id="lookup",
        handler="example.handler",
        config={"value": "{{ missing_node.id }}"},
    )

    with pytest.raises(TemplateResolutionError, match="unavailable dependency output"):
        NodeInputResolver().resolve(node, execution_input={}, dependency_outputs={})


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("{{ get_users.2.id }}", "missing output"),
        ("{{ get_users.name }}", "missing output"),
        ("{{ get_user.profile.name }}", "missing output"),
    ],
)
def test_resolve_rejects_missing_nested_output_path(template: str, message: str) -> None:
    node = WorkflowNode(id="lookup", handler="example.handler", config={"value": template})

    with pytest.raises(TemplateResolutionError, match=message):
        NodeInputResolver().resolve(
            node,
            execution_input={},
            dependency_outputs={
                "get_users": [{"id": 1}],
                "get_user": {"profile": {}},
            },
        )


def test_resolve_does_not_mutate_dependency_outputs() -> None:
    outputs = {"get_user": {"profile": {"name": "Ada"}, "tags": ["admin"]}}
    node = WorkflowNode(
        id="copy",
        handler="example.handler",
        config={"profile": "{{ get_user.profile }}", "tags": "{{ get_user.tags }}"},
    )

    result = NodeInputResolver().resolve(node, execution_input={}, dependency_outputs=outputs)
    profile = result["profile"]
    tags = result["tags"]
    assert isinstance(profile, dict)
    assert isinstance(tags, list)
    profile["name"] = "Changed"
    tags.append("changed")

    assert outputs == {"get_user": {"profile": {"name": "Ada"}, "tags": ["admin"]}}


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
