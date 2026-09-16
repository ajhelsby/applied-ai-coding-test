"""Shared fixtures for domain tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.domain.models.workflow import Workflow


@pytest.fixture
def workflow_from_nodes() -> Callable[[list[dict[str, Any]]], Workflow]:
    """Build an immutable workflow model from raw node definitions."""

    def build(nodes: list[dict[str, Any]]) -> Workflow:
        return Workflow.model_validate({"name": "test-workflow", "dag": {"nodes": nodes}})

    return build
