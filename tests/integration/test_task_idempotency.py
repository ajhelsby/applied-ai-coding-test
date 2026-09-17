"""Integration coverage for duplicate Redis task delivery."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

import pytest
import redis
from fastapi.testclient import TestClient

from app.messaging.redis.streams import WORKFLOW_TASKS_GROUP, WORKFLOW_TASKS_STREAM
from app.messaging.task_messages import NodeTaskMessage
from tests.integration.fixtures.infrastructure import InfrastructureConfig
from tests.integration.fixtures.lifecycle import (
    ServiceProcess,
    running_application_services,
    running_application_worker_cluster,
)
from tests.integration.fixtures.polling import (
    wait_for_node_status,
    wait_for_workflow_status,
)
from tests.integration.fixtures.task_delivery import (
    inspect_task_persistence,
    publish_task_deliveries,
    read_completion_stream,
    read_execution_counter,
    read_task_stream,
)

pytestmark = pytest.mark.integration

_POLL_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.05


def _wait_for(predicate: Callable[[], bool], expectation: str) -> None:
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out waiting for {expectation}.")
        time.sleep(min(_POLL_INTERVAL_SECONDS, deadline - time.monotonic()))


def _workflow(
    api_client: TestClient,
    nodes: list[dict[str, object]],
    *,
    input_data: dict[str, object] | None = None,
) -> UUID:
    response = api_client.post(
        "/workflow",
        json={"name": f"idempotency-integration-{uuid4()}", "dag": {"nodes": nodes}},
    )
    assert response.status_code == 201, response.text
    execution_id = UUID(response.json()["execution_id"])
    trigger = api_client.post(
        f"/workflow/trigger/{execution_id}",
        json={"input": input_data or {}},
    )
    assert trigger.status_code == 202, trigger.text
    return execution_id


def _workflow_fetcher(api_client: TestClient, execution_id: UUID) -> Callable[[], object]:
    def fetch() -> object:
        return api_client.get(f"/workflows/{execution_id}").json()

    return fetch


def _barrier_node(
    node_id: str,
    barrier_name: str,
    counter_name: str,
    dependencies: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "handler": "integration_barrier",
        "dependencies": dependencies or [],
        "config": {
            "barrier": {"name": barrier_name, "participant": node_id},
            "execution_counter": counter_name,
        },
    }


def _task_for_node(
    infrastructure: InfrastructureConfig,
    node_id: str,
) -> tuple[str, NodeTaskMessage]:
    found: list[tuple[str, NodeTaskMessage]] = []

    def find_task() -> bool:
        found.clear()
        for message_id, fields in read_task_stream(infrastructure):
            if fields.get("node_id") == node_id:
                found.append((message_id, NodeTaskMessage.from_stream_fields(fields)))
        return bool(found)

    _wait_for(find_task, f"the task delivery for node {node_id!r}")
    return found[-1]


def _pending_count(infrastructure: InfrastructureConfig) -> int:
    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        pending = client.xpending(WORKFLOW_TASKS_STREAM, WORKFLOW_TASKS_GROUP)
        return int(pending["pending"])
    finally:
        client.close()


def _completion_count(infrastructure: InfrastructureConfig, task_id: str) -> int:
    return sum(
        fields.get("task_id") == task_id for _, fields in read_completion_stream(infrastructure)
    )


def _diagnostics(
    orchestrator: ServiceProcess,
    worker: ServiceProcess,
) -> Callable[[], str]:
    def describe() -> str:
        return f"orchestrator:\n{orchestrator.output()}\nworker:\n{worker.output()}"

    return describe


def test_sequential_duplicate_delivery_executes_handler_once(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
    integration_infrastructure: InfrastructureConfig,
) -> None:
    orchestrator, worker = application_services
    barrier = f"sequential-{uuid4()}"
    counter = f"sequential-{uuid4()}"
    execution_id = _workflow(api_client, [_barrier_node("A", barrier, counter)])
    _, task = _task_for_node(integration_infrastructure, "A")
    _wait_for(
        lambda: _arrival_count(integration_infrastructure, barrier) == 1,
        "the first handler arrival",
    )
    _release(integration_infrastructure, barrier, "A")
    fetch = _workflow_fetcher(api_client, execution_id)
    wait_for_node_status(
        fetch,
        str(execution_id),
        "A",
        "COMPLETED",
        diagnostics=_diagnostics(orchestrator, worker),
    )
    publish_task_deliveries(integration_infrastructure, task)
    _wait_for(
        lambda: _pending_count(integration_infrastructure) == 0,
        "the sequential duplicate to be acknowledged",
    )

    snapshot = inspect_task_persistence(integration_infrastructure, task.task_id, task.attempt_id)
    assert read_execution_counter(integration_infrastructure, counter) == 1
    assert snapshot.attempt is not None and snapshot.attempt[3] == "completed"
    assert snapshot.node_execution is not None and snapshot.node_execution[2] == "completed"
    assert snapshot.node_execution[3] == {
        "barrier": barrier,
        "participant": "A",
        "status": "released",
    }
    assert _completion_count(integration_infrastructure, task.task_id) == 1


def test_concurrent_duplicate_delivery_claims_once(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
    application_worker_cluster: tuple[ServiceProcess, ...],
    integration_infrastructure: InfrastructureConfig,
) -> None:
    orchestrator, worker = application_services
    barrier = f"concurrent-{uuid4()}"
    counter = f"concurrent-{uuid4()}"
    execution_id = _workflow(api_client, [_barrier_node("A", barrier, counter)])
    first_message_id, task = _task_for_node(integration_infrastructure, "A")
    duplicate_ids = publish_task_deliveries(integration_infrastructure, task)
    worker_processes = (worker, *application_worker_cluster)
    _wait_for(
        lambda: _deliveries_observed_by_multiple_workers(
            worker_processes, (first_message_id, *duplicate_ids)
        ),
        "both physical duplicate deliveries to be observed",
    )
    _release(integration_infrastructure, barrier, "A")
    fetch = _workflow_fetcher(api_client, execution_id)
    wait_for_node_status(
        fetch,
        str(execution_id),
        "A",
        "COMPLETED",
        diagnostics=_diagnostics(orchestrator, worker),
    )
    assert read_execution_counter(integration_infrastructure, counter) == 1
    assert _completion_count(integration_infrastructure, task.task_id) == 1


def test_duplicate_after_completion_replays_safely(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
    integration_infrastructure: InfrastructureConfig,
) -> None:
    orchestrator, worker = application_services
    barrier = f"completed-{uuid4()}"
    counter = f"completed-{uuid4()}"
    execution_id = _workflow(api_client, [_barrier_node("A", barrier, counter)])
    _, task = _task_for_node(integration_infrastructure, "A")
    _release(integration_infrastructure, barrier, "A")
    fetch = _workflow_fetcher(api_client, execution_id)
    wait_for_workflow_status(
        fetch,
        str(execution_id),
        "COMPLETED",
        diagnostics=_diagnostics(orchestrator, worker),
    )
    publish_task_deliveries(integration_infrastructure, task)
    _wait_for(
        lambda: _pending_count(integration_infrastructure) == 0,
        "the completed duplicate to be acknowledged",
    )
    assert read_execution_counter(integration_infrastructure, counter) == 1
    assert _completion_count(integration_infrastructure, task.task_id) == 1


def test_multiple_duplicate_messages_produce_one_result(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
    integration_infrastructure: InfrastructureConfig,
) -> None:
    orchestrator, worker = application_services
    barrier = f"multiple-{uuid4()}"
    counter = f"multiple-{uuid4()}"
    execution_id = _workflow(api_client, [_barrier_node("A", barrier, counter)])
    _, task = _task_for_node(integration_infrastructure, "A")
    _release(integration_infrastructure, barrier, "A")
    fetch = _workflow_fetcher(api_client, execution_id)
    wait_for_workflow_status(
        fetch,
        str(execution_id),
        "COMPLETED",
        diagnostics=_diagnostics(orchestrator, worker),
    )
    physical_ids = publish_task_deliveries(integration_infrastructure, task, count=5)
    assert len(set(physical_ids)) == 5
    _wait_for(
        lambda: _pending_count(integration_infrastructure) == 0,
        "all duplicate messages to be acknowledged",
    )
    snapshot = inspect_task_persistence(integration_infrastructure, task.task_id, task.attempt_id)
    assert read_execution_counter(integration_infrastructure, counter) == 1
    assert snapshot.attempt is not None and snapshot.attempt[3] == "completed"
    assert _completion_count(integration_infrastructure, task.task_id) == 1


def test_interrupted_worker_task_is_reclaimed(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKER_RECLAIM_IDLE_MS", "500")
    monkeypatch.setenv("WORKER_TASK_CLAIM_LEASE_SECONDS", "0.05")
    with running_application_services(integration_infrastructure) as (orchestrator, worker):
        barrier = f"recovery-{uuid4()}"
        counter = f"recovery-{uuid4()}"
        execution_id = _workflow(api_client, [_barrier_node("A", barrier, counter)])
        _, task = _task_for_node(integration_infrastructure, "A")
        _wait_for(
            lambda: _arrival_count(integration_infrastructure, barrier) == 1,
            "the task to be claimed and started",
        )
        worker.stop()
        with running_application_worker_cluster(integration_infrastructure, worker_count=1):
            _wait_for(
                lambda: _arrival_count(integration_infrastructure, barrier) >= 2,
                "the claimed task to be reclaimed",
            )
            _release(integration_infrastructure, barrier, "A")
            fetch = _workflow_fetcher(api_client, execution_id)
            wait_for_node_status(
                fetch,
                str(execution_id),
                "A",
                "COMPLETED",
                diagnostics=lambda: f"orchestrator:\n{orchestrator.output()}",
            )

        snapshot = inspect_task_persistence(
            integration_infrastructure, task.task_id, task.attempt_id
        )
        assert snapshot.attempt is not None and snapshot.attempt[3] == "completed"
        assert _completion_count(integration_infrastructure, task.task_id) == 1


def test_duplicate_downstream_delivery_does_not_duplicate_workflow_execution(
    api_client: TestClient,
    application_services: tuple[ServiceProcess, ServiceProcess],
    integration_infrastructure: InfrastructureConfig,
) -> None:
    orchestrator, worker = application_services
    barrier = f"workflow-{uuid4()}"
    counter = f"workflow-{uuid4()}"
    execution_id = _workflow(
        api_client,
        [
            {"id": "A", "handler": "input", "dependencies": []},
            _barrier_node("B", barrier, counter, ["A"]),
            {
                "id": "C",
                "handler": "call_external_service",
                "dependencies": ["B"],
                "config": {"url": "https://workflow.example/{{ B.status }}"},
            },
        ],
    )
    _, task_b = _task_for_node(integration_infrastructure, "B")
    publish_task_deliveries(integration_infrastructure, task_b)
    _release(integration_infrastructure, barrier, "B")
    fetch = _workflow_fetcher(api_client, execution_id)
    completed = wait_for_workflow_status(
        fetch,
        str(execution_id),
        "COMPLETED",
        diagnostics=_diagnostics(orchestrator, worker),
    )
    nodes = completed.get("nodes")
    assert isinstance(nodes, list)
    statuses: dict[str, str] = {}
    for node in nodes:
        assert isinstance(node, Mapping)
        node_id = node.get("node_id")
        status = node.get("status")
        assert isinstance(node_id, str)
        assert isinstance(status, str)
        statuses[node_id] = status
    assert statuses == {"A": "COMPLETED", "B": "COMPLETED", "C": "COMPLETED"}
    assert read_execution_counter(integration_infrastructure, counter) == 1
    assert _completion_count(integration_infrastructure, task_b.task_id) == 1


def _arrival_count(infrastructure: InfrastructureConfig, barrier: str) -> int:
    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        return int(client.xlen(f"integration.barrier:{barrier}:arrivals"))
    finally:
        client.close()


def _deliveries_observed_by_multiple_workers(
    workers: tuple[ServiceProcess, ...],
    message_ids: tuple[str, ...],
) -> bool:
    owners = {
        index
        for index, worker in enumerate(workers)
        if any(message_id in worker.output() for message_id in message_ids)
    }
    observed = {
        message_id
        for message_id in message_ids
        if any(message_id in worker.output() for worker in workers)
    }
    return len(owners) >= 2 and len(observed) == len(message_ids)


def _release(infrastructure: InfrastructureConfig, barrier: str, participant: str) -> None:
    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        client.xadd(
            f"integration.barrier:{barrier}:releases",
            {"participant": participant},
        )
    finally:
        client.close()
