from __future__ import annotations

import pytest

from app.domain.templates.parser import (
    TemplateParser,
    TemplateReference,
    TemplateResolutionError,
)


def test_parse_full_reference() -> None:
    result = TemplateParser().parse("{{ get_user.id }}")

    assert result == TemplateReference(node_id="get_user", path=("id",))


def test_parse_nested_reference_with_whitespace() -> None:
    result = TemplateParser().parse("{{ get_user . profile . name }}")

    assert result == TemplateReference(
        node_id="get_user",
        path=("profile", "name"),
    )


def test_parse_multiple_embedded_references() -> None:
    result = TemplateParser().parse("User {{ get_user.id }} has {{ get_user.role }} access.")

    assert result == (
        "User ",
        TemplateReference(node_id="get_user", path=("id",)),
        " has ",
        TemplateReference(node_id="get_user", path=("role",)),
        " access.",
    )


def test_parse_non_template_string_unchanged() -> None:
    value = "plain input"

    assert TemplateParser().parse(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "{{ get_user }}",
        "{{ .id }}",
        "{{ get_user. }}",
        "{{ get_user.id",
        "get_user.id }}",
        "{{ get_user.id | __import__('os').system('whoami') }}",
        "{{ __import__('os').system('whoami').result }}",
    ],
)
def test_parse_rejects_malformed_or_executable_content(value: str) -> None:
    with pytest.raises(TemplateResolutionError, match="Malformed template expression"):
        TemplateParser().parse(value)


def test_embedded_parse_result_is_structured_without_lookup() -> None:
    result = TemplateParser().parse("id={{ get_user.id }}")

    assert isinstance(result, tuple)
    assert result == (
        "id=",
        TemplateReference(node_id="get_user", path=("id",)),
    )
