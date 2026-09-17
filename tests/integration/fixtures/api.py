"""Reusable helpers for exercising the workflow API through HTTP."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

import redis
from fastapi.testclient import TestClient
from httpx import Response

from tests.integration.fixtures.infrastructure import InfrastructureConfig

JsonObject = dict[str, object]


def submit_workflow(
    api_client: TestClient,
    nodes: Sequence[Mapping[str, object]],
    *,
    name_prefix: str = "integration-workflow",
) -> UUID:
    """Submit a workflow definition and return its created execution ID."""

    response = api_client.post(
        "/workflow",
        json={
            "name": f"{name_prefix}-{uuid4()}",
            "dag": {"nodes": list(nodes)},
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    execution_id = payload.get("execution_id")
    assert isinstance(execution_id, str)
    return UUID(execution_id)


def trigger_workflow(
    api_client: TestClient,
    execution_id: UUID,
    *,
    input_data: JsonObject | None = None,
) -> Response:
    """Trigger an execution through the public API."""

    response = api_client.post(
        f"/workflow/trigger/{execution_id}",
        json={"input": input_data or {}},
    )
    assert response.status_code == 202, response.text
    assert response.json()["execution_id"] == str(execution_id)
    return response


def get_workflow_status(api_client: TestClient, execution_id: UUID) -> JsonObject:
    """Retrieve a workflow status payload through the public API."""

    response = api_client.get(f"/workflows/{execution_id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def get_workflow_results(api_client: TestClient, execution_id: UUID) -> JsonObject:
    """Retrieve a workflow results payload through the public API."""

    response = api_client.get(f"/workflows/{execution_id}/results")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def redis_stream_lengths(
    infrastructure: InfrastructureConfig,
    streams: Sequence[str],
) -> dict[str, int]:
    """Return Redis stream lengths for side-effect assertions."""

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        return {stream: int(client.xlen(stream)) for stream in streams}
    finally:
        client.close()
