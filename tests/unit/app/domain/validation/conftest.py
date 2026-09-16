"""Shared fixtures for workflow validation tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def valid_workflow() -> dict[str, Any]:
    """Return a valid workflow definition for validation-rule tests."""

    return {
        "name": "Parallel API Fetcher",
        "dag": {
            "nodes": [
                {"id": "input", "handler": "input", "dependencies": []},
                {
                    "id": "get_user",
                    "handler": "call_external_service",
                    "dependencies": ["input"],
                    "config": {"url": "https://example.test/users"},
                },
                {
                    "id": "get_posts",
                    "handler": "call_external_service",
                    "dependencies": ["input"],
                    "config": {"url": "https://example.test/posts"},
                },
                {
                    "id": "output",
                    "handler": "output",
                    "dependencies": ["get_user", "get_posts"],
                },
            ]
        },
    }
