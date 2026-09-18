"""Representative workflow definitions for Docker topology tests."""

from __future__ import annotations


def diamond_workflow_nodes(*, latency_ms: int = 500) -> list[dict[str, object]]:
    """Return an A -> (B, C) -> D fan-out/fan-in workflow."""

    return [
        {"id": "A", "handler": "input", "dependencies": []},
        {
            "id": "B",
            "handler": "call_external_service",
            "dependencies": ["A"],
            "config": {
                "url": "https://docker-branch-b.example/{{ A.value }}",
                "latency_ms": latency_ms,
            },
        },
        {
            "id": "C",
            "handler": "call_external_service",
            "dependencies": ["A"],
            "config": {
                "url": "https://docker-branch-c.example/{{ A.value }}",
                "latency_ms": latency_ms,
            },
        },
        {
            "id": "D",
            "handler": "call_external_service",
            "dependencies": ["B", "C"],
            "config": {
                "url": "https://docker-join.example",
                "branches": {
                    "b": "{{ B.input.url }}",
                    "c": "{{ C.input.url }}",
                },
            },
        },
    ]
