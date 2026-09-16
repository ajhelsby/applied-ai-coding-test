"""End-to-end integration coverage for a successful linear workflow."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.integration.fixtures.lifecycle import ServiceProcess
from tests.integration.fixtures.polling import (
    wait_for_node_status,
    wait_for_workflow_status,
)

pytestmark = pytest.mark.integration


def test_linear_workflow_executes_asynchronously(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
) -> None:
    """Submit, trigger, and retrieve a real A -> B -> C workflow."""

    del application_services
    workflow_name = f"linear-integration-{uuid4()}"
    response = api_client.post(
        "/workflow",
        json={
            "name": workflow_name,
            "dag": {
                "nodes": [
                    {"id": "A", "handler": "input", "dependencies": []},
                    {
                        "id": "B",
                        "handler": "llm_service",
                        "dependencies": ["A"],
                        "config": {"prompt": "B received {{ A.value }}"},
                    },
                    {
                        "id": "C",
                        "handler": "llm_service",
                        "dependencies": ["A", "B"],
                        "config": {"prompt": "C received {{ B.response }} from {{ A.value }}"},
                    },
                ]
            },
        },
    )
    assert response.status_code == 201
    execution_id = UUID(response.json()["execution_id"])

    trigger_response = api_client.post(
        f"/workflow/trigger/{execution_id}",
        json={"input": {"value": "integration-value"}},
    )
    assert trigger_response.status_code == 202
    assert trigger_response.json()["execution_id"] == str(execution_id)

    def fetch_status() -> object:
        return api_client.get(f"/workflows/{execution_id}").json()

    after_a = wait_for_node_status(fetch_status, str(execution_id), "A", "COMPLETED")
    after_b = wait_for_node_status(fetch_status, str(execution_id), "B", "COMPLETED")

    node_a = next(node for node in after_b["nodes"] if node["node_id"] == "A")
    node_b = next(node for node in after_b["nodes"] if node["node_id"] == "B")
    assert node_a["status"] == "COMPLETED"
    assert node_b["status"] == "COMPLETED"
    assert node_a["completed_at"] is not None
    assert node_b["started_at"] is not None
    assert datetime.fromisoformat(node_a["completed_at"]) <= datetime.fromisoformat(
        node_b["started_at"]
    )
    assert after_a["nodes"]

    completed = wait_for_workflow_status(
        fetch_status,
        str(execution_id),
        "COMPLETED",
    )
    assert completed["status"] == "COMPLETED"

    results_response = api_client.get(f"/workflows/{execution_id}/results")
    assert results_response.status_code == 200
    results_payload = results_response.json()
    assert results_payload["status"] == "COMPLETED"

    results = {result["node_id"]: result for result in results_payload["results"]}
    assert set(results) == {"A", "B", "C"}
    assert results["A"]["output_data"] == {"value": "integration-value"}
    assert "integration-value" in results["B"]["output_data"]["response"]
    assert results["B"]["output_data"]["response"] in results["C"]["output_data"]["response"]
    assert "integration-value" in results["C"]["output_data"]["response"]
