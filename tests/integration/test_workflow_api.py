"""Integration coverage for the public workflow HTTP API."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID, uuid4

import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.messaging.redis.streams import (
    WORKFLOW_EVENTS_STREAM,
    WORKFLOW_TASK_COMPLETIONS_STREAM,
    WORKFLOW_TASKS_STREAM,
)
from tests.integration.fixtures.api import (
    get_workflow_results,
    get_workflow_status,
    redis_stream_lengths,
    submit_workflow,
    trigger_workflow,
)
from tests.integration.fixtures.diagnostics import (
    inspect_database,
    inspect_redis_streams,
)
from tests.integration.fixtures.infrastructure import InfrastructureConfig
from tests.integration.fixtures.lifecycle import ServiceProcess
from tests.integration.fixtures.polling import wait_for_workflow_status

pytestmark = pytest.mark.integration

_WORKFLOW_STREAMS = (
    WORKFLOW_EVENTS_STREAM,
    WORKFLOW_TASKS_STREAM,
    WORKFLOW_TASK_COMPLETIONS_STREAM,
)


def _input_node(node_id: str = "input") -> dict[str, object]:
    return {"id": node_id, "handler": "input", "dependencies": []}


def _external_node(
    node_id: str = "fetch",
    *,
    dependencies: list[str] | None = None,
    latency_ms: int = 0,
) -> dict[str, object]:
    return {
        "id": node_id,
        "handler": "call_external_service",
        "dependencies": dependencies or [],
        "config": {
            "url": "https://example.test/{{ input.value }}",
            "latency_ms": latency_ms,
        },
    }


def _workflow_payload(nodes: list[dict[str, object]]) -> dict[str, object]:
    return {"name": f"api-integration-{uuid4()}", "dag": {"nodes": nodes}}


def _database_counts(infrastructure: InfrastructureConfig) -> dict[str, int]:
    connection = psycopg2.connect(infrastructure.database_url.replace("+asyncpg", ""))
    try:
        with connection.cursor() as cursor:
            counts: dict[str, int] = {}
            for table in ("workflows", "workflow_executions", "node_executions"):
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                row = cursor.fetchone()
                assert row is not None
                counts[table] = int(row[0])
            return counts
    finally:
        connection.close()


def _persisted_workflow(
    infrastructure: InfrastructureConfig,
    execution_id: UUID,
) -> tuple[object, object, object]:
    connection = psycopg2.connect(infrastructure.database_url.replace("+asyncpg", ""))
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT w.name, w.dag_definition, e.status
                FROM workflows AS w
                JOIN workflow_executions AS e ON e.workflow_id = w.workflow_id
                WHERE e.execution_id = %s
                """,
                (execution_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            return row
    finally:
        connection.close()


def test_submit_workflow_persists_pending_execution_without_publishing_tasks(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
) -> None:
    nodes = [_input_node(), _external_node(dependencies=["input"])]
    before_streams = redis_stream_lengths(integration_infrastructure, _WORKFLOW_STREAMS)

    response = api_client.post("/workflow", json=_workflow_payload(nodes))

    assert response.status_code == 201
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    execution_id = UUID(payload["execution_id"])
    assert payload["name"].startswith("api-integration-")
    assert payload["created_at"]

    name, dag_definition, persisted_status = _persisted_workflow(
        integration_infrastructure, execution_id
    )
    assert name == payload["name"]
    assert isinstance(dag_definition, dict)
    persisted_nodes = dag_definition["nodes"]
    assert isinstance(persisted_nodes, list)
    assert [
        {
            "id": node["id"],
            "handler": node["handler"],
            "dependencies": node["dependencies"],
            "config": node["config"],
        }
        for node in persisted_nodes
    ] == nodes
    assert persisted_status == "pending"
    assert get_workflow_status(api_client, execution_id)["status"] == "PENDING"
    assert redis_stream_lengths(integration_infrastructure, _WORKFLOW_STREAMS) == before_streams


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"dag": {"nodes": []}}, None),
        ({"name": 42, "dag": {"nodes": []}}, None),
        (
            _workflow_payload([{"id": "bad node", "handler": "input", "dependencies": []}]),
            "invalid_node_id",
        ),
        (
            _workflow_payload(
                [
                    _input_node("duplicate"),
                    _input_node("duplicate"),
                ]
            ),
            "duplicate_node_id",
        ),
        (
            _workflow_payload([{"id": "fetch", "handler": "input", "dependencies": ["missing"]}]),
            "unknown_dependency",
        ),
        (
            _workflow_payload([{"id": "input", "handler": "input", "dependencies": ["input"]}]),
            "self_dependency",
        ),
        (
            _workflow_payload(
                [
                    {"id": "A", "handler": "input", "dependencies": ["B"]},
                    {"id": "B", "handler": "input", "dependencies": ["A"]},
                ]
            ),
            "cyclic_dependency",
        ),
        (
            _workflow_payload(
                [
                    {"id": "A", "handler": "input", "dependencies": ["C"]},
                    {"id": "B", "handler": "input", "dependencies": ["A"]},
                    {"id": "C", "handler": "input", "dependencies": ["B"]},
                ]
            ),
            "cyclic_dependency",
        ),
    ],
)
def test_invalid_workflow_submission_has_no_persistence_or_redis_side_effects(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
    payload: dict[str, object],
    expected_code: str | None,
) -> None:
    before_counts = _database_counts(integration_infrastructure)
    before_streams = redis_stream_lengths(integration_infrastructure, _WORKFLOW_STREAMS)

    response = api_client.post("/workflow", json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert isinstance(body, dict)
    if expected_code is not None:
        assert expected_code in {item["code"] for item in body["errors"]}
    else:
        assert "detail" in body
    assert _database_counts(integration_infrastructure) == before_counts
    assert redis_stream_lengths(integration_infrastructure, _WORKFLOW_STREAMS) == before_streams


def test_malformed_submission_json_has_no_side_effects(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
) -> None:
    before_counts = _database_counts(integration_infrastructure)
    before_streams = redis_stream_lengths(integration_infrastructure, _WORKFLOW_STREAMS)

    response = api_client.post(
        "/workflow",
        content=b'{"name": "invalid",',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert isinstance(response.json().get("detail"), list)
    assert _database_counts(integration_infrastructure) == before_counts
    assert redis_stream_lengths(integration_infrastructure, _WORKFLOW_STREAMS) == before_streams


def test_trigger_accepts_input_and_runs_asynchronously(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
) -> None:
    orchestrator, worker = application_services
    execution_id = submit_workflow(
        api_client,
        [_input_node(), _external_node(dependencies=["input"], latency_ms=1_000)],
    )

    trigger_response = trigger_workflow(
        api_client,
        execution_id,
        input_data={"value": "integration-value"},
    )

    assert trigger_response.headers["content-type"].startswith("application/json")
    assert trigger_response.json()["status"] == "running"
    running = get_workflow_status(api_client, execution_id)
    assert running["status"] == "RUNNING"
    assert get_workflow_results(api_client, execution_id)["results"] is None

    completed = wait_for_workflow_status(
        lambda: get_workflow_status(api_client, execution_id),
        str(execution_id),
        "COMPLETED",
        diagnostics=lambda: f"{orchestrator.output()}\n{worker.output()}",
    )
    assert completed["status"] == "COMPLETED"


def test_trigger_rejects_unknown_malformed_and_repeated_execution_ids(
    api_client: TestClient,
) -> None:
    unknown_id = UUID("00000000-0000-0000-0000-000000000000")
    unknown_response = api_client.post(f"/workflow/trigger/{unknown_id}")
    assert unknown_response.status_code == 404
    assert unknown_response.json()["error_code"] == "workflow_execution_not_found"

    malformed_response = api_client.post("/workflow/trigger/not-a-uuid")
    assert malformed_response.status_code == 422
    assert "detail" in malformed_response.json()

    execution_id = submit_workflow(api_client, [_input_node()])
    first_response = api_client.post(f"/workflow/trigger/{execution_id}")
    second_response = api_client.post(f"/workflow/trigger/{execution_id}")
    assert first_response.status_code == 202
    assert second_response.status_code == 422
    assert second_response.json()["error_code"] == "workflow_execution_not_triggerable"


def test_status_and_results_reject_unknown_and_malformed_execution_ids(
    api_client: TestClient,
) -> None:
    unknown_id = UUID("00000000-0000-0000-0000-000000000000")
    for path in (f"/workflows/{unknown_id}", f"/workflows/{unknown_id}/results"):
        response = api_client.get(path)
        assert response.status_code == 404

    for path in ("/workflows/not-a-uuid", "/workflows/not-a-uuid/results"):
        response = api_client.get(path)
        assert response.status_code == 422
        assert "detail" in response.json()


def test_status_and_results_reads_are_read_only_for_pending_execution(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
) -> None:
    execution_id = submit_workflow(api_client, [_input_node()])
    before_database = inspect_database(integration_infrastructure, execution_id)
    before_streams = inspect_redis_streams(integration_infrastructure, _WORKFLOW_STREAMS)

    status = get_workflow_status(api_client, execution_id)
    results = get_workflow_results(api_client, execution_id)

    assert status["status"] == "PENDING"
    assert results["status"] == "PENDING"
    assert results["message"]
    assert results["results"] is None
    assert inspect_database(integration_infrastructure, execution_id) == before_database
    assert inspect_redis_streams(integration_infrastructure, _WORKFLOW_STREAMS) == before_streams


def test_status_and_results_report_completed_nodes_and_resolved_templates(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
) -> None:
    orchestrator, worker = application_services
    execution_id = submit_workflow(
        api_client,
        [
            _input_node(),
            {
                "id": "fetch",
                "handler": "call_external_service",
                "dependencies": ["input"],
                "config": {"url": "https://example.test/{{ input.value }}"},
            },
        ],
    )
    trigger_workflow(api_client, execution_id, input_data={"value": "resolved"})

    completed = wait_for_workflow_status(
        lambda: get_workflow_status(api_client, execution_id),
        str(execution_id),
        "COMPLETED",
        diagnostics=lambda: f"{orchestrator.output()}\n{worker.output()}",
    )
    assert {
        node["node_id"]: node["status"] for node in completed["nodes"] if isinstance(node, Mapping)
    } == {"input": "COMPLETED", "fetch": "COMPLETED"}

    results = get_workflow_results(api_client, execution_id)
    assert results["status"] == "COMPLETED"
    assert results["message"] is None
    result_by_node = {
        result["node_id"]: result for result in results["results"] if isinstance(result, Mapping)
    }
    assert result_by_node["input"]["output_data"] == {"value": "resolved"}
    assert result_by_node["fetch"]["output_data"]["input"] == {
        "url": "https://example.test/resolved"
    }


def test_workflow_lifecycle_is_available_through_public_http_contract(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
) -> None:
    orchestrator, worker = application_services
    submission = api_client.post(
        "/workflow",
        json=_workflow_payload(
            [
                _input_node(),
                {
                    "id": "fetch",
                    "handler": "call_external_service",
                    "dependencies": ["input"],
                    "config": {"url": "https://example.test/{{ input.value }}"},
                },
            ]
        ),
    )
    assert submission.status_code == 201
    execution_id = UUID(submission.json()["execution_id"])

    initial_status = api_client.get(f"/workflows/{execution_id}")
    assert initial_status.status_code == 200
    assert initial_status.json()["status"] == "PENDING"

    trigger = api_client.post(
        f"/workflow/trigger/{execution_id}",
        json={"input": {"value": "lifecycle"}},
    )
    assert trigger.status_code == 202

    completed = wait_for_workflow_status(
        lambda: api_client.get(f"/workflows/{execution_id}").json(),
        str(execution_id),
        "COMPLETED",
        diagnostics=lambda: f"{orchestrator.output()}\n{worker.output()}",
    )
    assert completed["execution_id"] == str(execution_id)

    result_response = api_client.get(f"/workflows/{execution_id}/results")
    assert result_response.status_code == 200
    assert result_response.json()["status"] == "COMPLETED"
