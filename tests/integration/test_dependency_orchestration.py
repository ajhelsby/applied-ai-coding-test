"""Integration coverage for dependency-based workflow orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.integration.fixtures.lifecycle import ServiceProcess
from tests.integration.fixtures.polling import (
    WorkflowFetcher,
    WorkflowPayload,
    wait_for_nodes_status,
    wait_for_workflow_status,
)

JsonObject = dict[str, object]


def submit_and_trigger_workflow(
    api_client: TestClient,
    nodes: list[JsonObject],
    input_data: JsonObject | None = None,
) -> UUID:
    """Create and trigger one workflow through the public API."""

    response = api_client.post(
        "/workflow",
        json={
            "name": f"dependency-integration-{uuid4()}",
            "dag": {"nodes": nodes},
        },
    )
    assert response.status_code == 201, response.text
    execution_id = UUID(response.json()["execution_id"])

    trigger_response = api_client.post(
        f"/workflow/trigger/{execution_id}",
        json={"input": input_data or {}},
    )
    assert trigger_response.status_code == 202, trigger_response.text
    assert trigger_response.json()["execution_id"] == str(execution_id)
    return execution_id


def workflow_fetcher(api_client: TestClient, execution_id: UUID) -> WorkflowFetcher:
    """Build a status fetcher for one execution."""

    def fetch() -> object:
        response = api_client.get(f"/workflows/{execution_id}")
        assert response.status_code == 200, response.text
        return response.json()

    return fetch


def service_diagnostics(
    orchestrator: ServiceProcess,
    worker: ServiceProcess,
) -> Callable[[], str]:
    """Build diagnostics for asynchronous service failures."""

    def diagnostics() -> str:
        return f"orchestrator_output:\n{orchestrator.output()}\nworker_output:\n{worker.output()}"

    return diagnostics


def completed_results(
    api_client: TestClient,
    execution_id: UUID,
) -> dict[str, Mapping[str, object]]:
    """Fetch completed node results keyed by node ID."""

    response = api_client.get(f"/workflows/{execution_id}/results")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    results = payload["results"]
    assert isinstance(results, list)
    return {
        result["node_id"]: result
        for result in results
        if isinstance(result, Mapping) and isinstance(result.get("node_id"), str)
    }


def node_statuses(payload: WorkflowPayload) -> dict[str, str]:
    """Return persisted node statuses from a workflow status payload."""

    nodes = payload.get("nodes")
    assert isinstance(nodes, list)
    statuses: dict[str, str] = {}
    for node in nodes:
        assert isinstance(node, Mapping)
        node_id = node.get("node_id")
        status = node.get("status")
        assert isinstance(node_id, str)
        assert isinstance(status, str)
        statuses[node_id] = status
    return statuses


def test_pure_fan_out_dispatches_independent_branches_concurrently(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
) -> None:
    """Verify A enables B and C independently through the event-driven path."""

    orchestrator, worker = application_services
    diagnostics = service_diagnostics(orchestrator, worker)
    nodes: list[JsonObject] = [
        {"id": "A", "handler": "input", "dependencies": []},
        {
            "id": "B",
            "handler": "call_external_service",
            "dependencies": ["A"],
            "config": {
                "url": "https://branch-b.example/{{ A.value }}",
                "latency_ms": 500,
            },
        },
        {
            "id": "C",
            "handler": "call_external_service",
            "dependencies": ["A"],
            "config": {
                "url": "https://branch-c.example/{{ A.value }}",
                "latency_ms": 500,
            },
        },
    ]
    execution_id = submit_and_trigger_workflow(
        api_client,
        nodes,
        input_data={"value": "fan-out"},
    )
    fetch = workflow_fetcher(api_client, execution_id)

    running_branches = wait_for_nodes_status(
        fetch,
        str(execution_id),
        {"B": "RUNNING", "C": "RUNNING"},
        diagnostics=diagnostics,
    )
    statuses = node_statuses(running_branches)
    assert statuses["A"] == "COMPLETED"

    completed = wait_for_workflow_status(
        fetch,
        str(execution_id),
        "COMPLETED",
        diagnostics=diagnostics,
    )
    assert node_statuses(completed) == {"A": "COMPLETED", "B": "COMPLETED", "C": "COMPLETED"}

    results = completed_results(api_client, execution_id)
    assert set(results) == {"A", "B", "C"}
    assert results["A"]["output_data"] == {"value": "fan-out"}
    assert results["B"]["output_data"]["input"] == {
        "url": "https://branch-b.example/fan-out",
        "latency_ms": 500,
    }
    assert results["C"]["output_data"]["input"] == {
        "url": "https://branch-c.example/fan-out",
        "latency_ms": 500,
    }


@pytest.mark.parametrize("completion_order", [("A", "B"), ("B", "A")])
def test_pure_fan_in_waits_for_both_parents_and_passes_both_outputs(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
    completion_order: tuple[str, str],
) -> None:
    """Verify a fan-in node waits for either parent completion order."""

    orchestrator, worker = application_services
    diagnostics = service_diagnostics(orchestrator, worker)
    first_parent, second_parent = completion_order
    latencies = {first_parent: 0, second_parent: 2_000}
    nodes: list[JsonObject] = [
        {
            "id": "A",
            "handler": "call_external_service",
            "dependencies": [],
            "config": {
                "url": "https://parent-a.example",
                "latency_ms": latencies["A"],
            },
        },
        {
            "id": "B",
            "handler": "call_external_service",
            "dependencies": [],
            "config": {
                "url": "https://parent-b.example",
                "latency_ms": latencies["B"],
            },
        },
        {
            "id": "C",
            "handler": "call_external_service",
            "dependencies": ["A", "B"],
            "config": {
                "url": "https://fan-in.example",
                "latency_ms": 0,
                "parents": {
                    "a_url": "{{ A.input.url }}",
                    "b_url": "{{ B.input.url }}",
                },
            },
        },
    ]
    execution_id = submit_and_trigger_workflow(api_client, nodes)
    fetch = workflow_fetcher(api_client, execution_id)

    after_first_parent = wait_for_nodes_status(
        fetch,
        str(execution_id),
        {first_parent: "COMPLETED"},
        diagnostics=diagnostics,
    )
    after_first_parent_statuses = node_statuses(after_first_parent)
    assert after_first_parent_statuses[second_parent] != "COMPLETED"
    assert after_first_parent_statuses["C"] == "PENDING"

    completed = wait_for_workflow_status(
        fetch,
        str(execution_id),
        "COMPLETED",
        diagnostics=diagnostics,
    )
    assert node_statuses(completed) == {"A": "COMPLETED", "B": "COMPLETED", "C": "COMPLETED"}

    results = completed_results(api_client, execution_id)
    assert set(results) == {"A", "B", "C"}
    assert results["C"]["output_data"]["input"]["parents"] == {
        "a_url": "https://parent-a.example",
        "b_url": "https://parent-b.example",
    }


def test_diamond_fan_out_fan_in_waits_for_both_branches(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
) -> None:
    """Verify a diamond dispatches branches concurrently and joins once."""

    orchestrator, worker = application_services
    diagnostics = service_diagnostics(orchestrator, worker)
    nodes: list[JsonObject] = [
        {"id": "A", "handler": "input", "dependencies": []},
        {
            "id": "B",
            "handler": "call_external_service",
            "dependencies": ["A"],
            "config": {
                "url": "https://diamond-b.example/{{ A.value }}",
                "latency_ms": 100,
            },
        },
        {
            "id": "C",
            "handler": "call_external_service",
            "dependencies": ["A"],
            "config": {
                "url": "https://diamond-c.example/{{ A.value }}",
                "latency_ms": 700,
            },
        },
        {
            "id": "D",
            "handler": "call_external_service",
            "dependencies": ["B", "C"],
            "config": {
                "url": "https://diamond-d.example",
                "latency_ms": 0,
                "branches": {
                    "b": "{{ B.input.url }}",
                    "c": "{{ C.input.url }}",
                },
            },
        },
    ]
    execution_id = submit_and_trigger_workflow(
        api_client,
        nodes,
        input_data={"value": "diamond"},
    )
    fetch = workflow_fetcher(api_client, execution_id)

    running_branches = wait_for_nodes_status(
        fetch,
        str(execution_id),
        {"B": "RUNNING", "C": "RUNNING"},
        diagnostics=diagnostics,
    )
    assert node_statuses(running_branches)["D"] == "PENDING"

    after_b = wait_for_nodes_status(
        fetch,
        str(execution_id),
        {"B": "COMPLETED", "C": "RUNNING"},
        diagnostics=diagnostics,
    )
    assert node_statuses(after_b)["D"] == "PENDING"

    completed = wait_for_workflow_status(
        fetch,
        str(execution_id),
        "COMPLETED",
        diagnostics=diagnostics,
    )
    assert node_statuses(completed) == {
        "A": "COMPLETED",
        "B": "COMPLETED",
        "C": "COMPLETED",
        "D": "COMPLETED",
    }

    results = completed_results(api_client, execution_id)
    assert results["D"]["output_data"]["input"]["branches"] == {
        "b": "https://diamond-b.example/diamond",
        "c": "https://diamond-c.example/diamond",
    }
