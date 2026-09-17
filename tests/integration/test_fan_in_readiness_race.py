"""Integration coverage for concurrent fan-in readiness evaluation."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from redis import asyncio as aioredis

from tests.integration.fixtures.barriers import RedisBarrier, RedisBarrierTimeout
from tests.integration.fixtures.diagnostics import (
    DatabaseDiagnostics,
    format_diagnostics,
    inspect_database,
    inspect_redis_streams,
)
from tests.integration.fixtures.infrastructure import InfrastructureConfig
from tests.integration.fixtures.lifecycle import (
    ServiceProcess,
    running_application_service_cluster,
)
from tests.integration.fixtures.polling import (
    WorkflowFetcher,
    node_statuses,
    wait_for_nodes_status,
    wait_for_workflow_status,
)

pytestmark = pytest.mark.integration

JsonObject = dict[str, object]


def _workflow_fetcher(api_client: TestClient, execution_id: UUID) -> WorkflowFetcher:
    def fetch() -> object:
        response = api_client.get(f"/workflows/{execution_id}")
        assert response.status_code == 200, response.text
        return response.json()

    return fetch


def _service_diagnostics(
    orchestrators: tuple[ServiceProcess, ...],
    worker: ServiceProcess,
) -> str:
    orchestrator_output = "\n\n".join(
        f"{service.name}:\n{service.output()}" for service in orchestrators
    )
    return f"orchestrators:\n{orchestrator_output}\nworker:\n{worker.output()}"


async def _coordinate_race(
    infrastructure: InfrastructureConfig,
    parent_barrier_name: str,
    completion_barrier_name: str,
    downstream_barrier_name: str,
    parent_participants: Sequence[str],
) -> None:
    client = aioredis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        parent_barrier = RedisBarrier(client, parent_barrier_name, parent_participants)
        completion_barrier = RedisBarrier(client, completion_barrier_name, parent_participants)
        downstream_barrier = RedisBarrier(client, downstream_barrier_name, ("D",))

        await parent_barrier.wait_for_arrivals()
        await parent_barrier.release()
        await completion_barrier.wait_for_arrivals()
        await completion_barrier.release()
        await downstream_barrier.wait_for_arrivals()
        await downstream_barrier.release()
    finally:
        await client.close()


async def _coordinate_duplicate_race(
    infrastructure: InfrastructureConfig,
    parent_barrier_name: str,
    completion_barrier_name: str,
    downstream_barrier_name: str,
) -> None:
    client = aioredis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        parent_barrier = RedisBarrier(client, parent_barrier_name, ("B", "C"))
        completion_barrier = RedisBarrier(client, completion_barrier_name, ("B", "C"))
        downstream_barrier = RedisBarrier(client, downstream_barrier_name, ("D",))

        await parent_barrier.wait_for_arrivals()
        await parent_barrier.release()
        await completion_barrier.wait_for_arrivals()

        completion_entries = await client.xrange("workflow.task-completions")
        parent_completion = next(
            fields for _, fields in completion_entries if fields.get("node_id") == "B"
        )
        await client.xadd("workflow.task-completions", parent_completion)
        await completion_barrier.release()
        arrival_stream = _barrier_stream_names(completion_barrier_name)[0]
        arrivals = await client.xrange(arrival_stream)
        duplicate_arrival = await client.xread(
            streams={arrival_stream: arrivals[-1][0]},
            count=1,
            block=30_000,
        )
        if not duplicate_arrival:
            raise RedisBarrierTimeout(
                f"Timed out waiting for duplicate completion on barrier "
                f"{completion_barrier_name!r}."
            )
        await downstream_barrier.wait_for_arrivals()
        await downstream_barrier.release()
    finally:
        await client.close()


def _barrier_stream_names(name: str) -> tuple[str, str]:
    return (
        f"integration.barrier:{name}:arrivals",
        f"integration.barrier:{name}:releases",
    )


def _node_rows(
    rows: tuple[tuple[object, ...], ...],
    node_id: str,
    node_index: int,
) -> tuple[tuple[object, ...], ...]:
    return tuple(row for row in rows if row[node_index] == node_id)


def _task_outbox_rows(
    database: DatabaseDiagnostics,
    node_id: str,
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        row
        for row in database.outbox_events
        if row[1] == "workflow.task"
        and isinstance(row[4], Mapping)
        and row[4].get("node_id") == node_id
    )


def test_concurrent_diamond_fan_in_claims_downstream_once(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release both parent completions together and claim D exactly once."""

    completion_prefix = f"integration-completion-{uuid4()}"
    monkeypatch.setenv("INTEGRATION_COMPLETION_BARRIER_PREFIX", completion_prefix)
    monkeypatch.setenv("INTEGRATION_COMPLETION_BARRIER_NODES", "B,C")
    monkeypatch.setenv("INTEGRATION_BARRIER_TIMEOUT_SECONDS", "30")

    with running_application_service_cluster(integration_infrastructure) as (
        orchestrators,
        worker,
    ):
        for iteration in range(3):
            parent_barrier_name = f"parents-{uuid4()}"
            downstream_barrier_name = f"downstream-{uuid4()}"
            nodes: list[JsonObject] = [
                {"id": "A", "handler": "input", "dependencies": []},
                {
                    "id": "B",
                    "handler": "integration_barrier",
                    "dependencies": ["A"],
                    "config": {
                        "barrier": {
                            "name": parent_barrier_name,
                            "participant": "B",
                        }
                    },
                },
                {
                    "id": "C",
                    "handler": "integration_barrier",
                    "dependencies": ["A"],
                    "config": {
                        "barrier": {
                            "name": parent_barrier_name,
                            "participant": "C",
                        }
                    },
                },
                {
                    "id": "D",
                    "handler": "integration_barrier",
                    "dependencies": ["B", "C"],
                    "config": {
                        "barrier": {
                            "name": downstream_barrier_name,
                            "participant": "D",
                        }
                    },
                },
            ]
            response = api_client.post(
                "/workflow",
                json={"name": f"fan-in-race-{iteration}-{uuid4()}", "dag": {"nodes": nodes}},
            )
            assert response.status_code == 201, response.text
            execution_id = UUID(response.json()["execution_id"])
            trigger = api_client.post(
                f"/workflow/trigger/{execution_id}",
                json={"input": {"iteration": iteration}},
            )
            assert trigger.status_code == 202, trigger.text

            fetch = _workflow_fetcher(api_client, execution_id)

            def diagnostics() -> str:
                return _service_diagnostics(orchestrators, worker)

            running = wait_for_nodes_status(
                fetch,
                str(execution_id),
                {"B": "RUNNING", "C": "RUNNING"},
                diagnostics=diagnostics,
            )
            assert node_statuses(running)["D"] == "PENDING"

            try:
                asyncio.run(
                    _coordinate_race(
                        integration_infrastructure,
                        parent_barrier_name,
                        f"{completion_prefix}:{execution_id}",
                        downstream_barrier_name,
                        ("B", "C"),
                    )
                )
            except RedisBarrierTimeout as error:
                database = inspect_database(integration_infrastructure, execution_id)
                streams = inspect_redis_streams(
                    integration_infrastructure,
                    (
                        *_barrier_stream_names(parent_barrier_name),
                        *_barrier_stream_names(f"{completion_prefix}:{execution_id}"),
                        *_barrier_stream_names(downstream_barrier_name),
                        "workflow.task-completions",
                    ),
                )
                raise AssertionError(
                    f"Fan-in race coordination failed: {error}\n"
                    f"{format_diagnostics(database, streams)}\n{diagnostics()}"
                ) from error

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

            database = inspect_database(integration_infrastructure, execution_id)
            d_logical_tasks = _node_rows(database.logical_tasks, "D", 1)
            d_task_ids = {row[0] for row in d_logical_tasks}
            d_attempts = tuple(row for row in database.task_attempts if row[1] in d_task_ids)
            d_task_messages = _task_outbox_rows(database, "D")
            assert len(d_logical_tasks) == 1
            assert len(d_attempts) == 1
            assert len(d_task_messages) == 1

            streams = inspect_redis_streams(
                integration_infrastructure,
                (
                    *_barrier_stream_names(parent_barrier_name),
                    *_barrier_stream_names(f"{completion_prefix}:{execution_id}"),
                    *_barrier_stream_names(downstream_barrier_name),
                ),
            )
            assert len(streams[_barrier_stream_names(parent_barrier_name)[0]]) == 2
            completion_arrivals = _barrier_stream_names(f"{completion_prefix}:{execution_id}")[0]
            assert len(streams[completion_arrivals]) == 2
            assert len(streams[_barrier_stream_names(downstream_barrier_name)[0]]) == 1


def test_concurrent_three_parent_fan_in_claims_downstream_once(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release three independent parent completions together and claim D once."""

    completion_prefix = f"integration-three-parent-completion-{uuid4()}"
    monkeypatch.setenv("INTEGRATION_COMPLETION_BARRIER_PREFIX", completion_prefix)
    monkeypatch.setenv("INTEGRATION_COMPLETION_BARRIER_NODES", "A,B,C")
    monkeypatch.setenv("INTEGRATION_BARRIER_TIMEOUT_SECONDS", "30")

    with running_application_service_cluster(integration_infrastructure) as (
        orchestrators,
        worker,
    ):
        parent_barrier_name = f"three-parents-{uuid4()}"
        downstream_barrier_name = f"three-downstream-{uuid4()}"
        parent_ids = ("A", "B", "C")
        nodes: list[JsonObject] = [
            *[
                {
                    "id": node_id,
                    "handler": "integration_barrier",
                    "dependencies": [],
                    "config": {
                        "barrier": {
                            "name": parent_barrier_name,
                            "participant": node_id,
                        }
                    },
                }
                for node_id in parent_ids
            ],
            {
                "id": "D",
                "handler": "integration_barrier",
                "dependencies": list(parent_ids),
                "config": {
                    "barrier": {
                        "name": downstream_barrier_name,
                        "participant": "D",
                    }
                },
            },
        ]
        response = api_client.post(
            "/workflow",
            json={"name": f"three-parent-race-{uuid4()}", "dag": {"nodes": nodes}},
        )
        assert response.status_code == 201, response.text
        execution_id = UUID(response.json()["execution_id"])
        trigger = api_client.post(
            f"/workflow/trigger/{execution_id}",
            json={"input": {}},
        )
        assert trigger.status_code == 202, trigger.text

        fetch = _workflow_fetcher(api_client, execution_id)

        def diagnostics() -> str:
            return _service_diagnostics(orchestrators, worker)

        running = wait_for_nodes_status(
            fetch,
            str(execution_id),
            {node_id: "RUNNING" for node_id in parent_ids},
            diagnostics=diagnostics,
        )
        assert node_statuses(running)["D"] == "PENDING"

        try:
            asyncio.run(
                _coordinate_race(
                    integration_infrastructure,
                    parent_barrier_name,
                    f"{completion_prefix}:{execution_id}",
                    downstream_barrier_name,
                    parent_ids,
                )
            )
        except RedisBarrierTimeout as error:
            database = inspect_database(integration_infrastructure, execution_id)
            streams = inspect_redis_streams(
                integration_infrastructure,
                (
                    *_barrier_stream_names(parent_barrier_name),
                    *_barrier_stream_names(f"{completion_prefix}:{execution_id}"),
                    *_barrier_stream_names(downstream_barrier_name),
                    "workflow.task-completions",
                ),
            )
            raise AssertionError(
                f"Three-parent race coordination failed: {error}\n"
                f"{format_diagnostics(database, streams)}\n{diagnostics()}"
            ) from error

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

        database = inspect_database(integration_infrastructure, execution_id)
        d_logical_tasks = _node_rows(database.logical_tasks, "D", 1)
        d_task_ids = {row[0] for row in d_logical_tasks}
        d_attempts = tuple(row for row in database.task_attempts if row[1] in d_task_ids)
        assert len(d_logical_tasks) == 1
        assert len(d_attempts) == 1
        assert len(_task_outbox_rows(database, "D")) == 1

        streams = inspect_redis_streams(
            integration_infrastructure,
            (
                *_barrier_stream_names(parent_barrier_name),
                *_barrier_stream_names(f"{completion_prefix}:{execution_id}"),
                *_barrier_stream_names(downstream_barrier_name),
            ),
        )
        assert len(streams[_barrier_stream_names(parent_barrier_name)[0]]) == 3
        completion_arrivals = _barrier_stream_names(f"{completion_prefix}:{execution_id}")[0]
        assert len(streams[completion_arrivals]) == 3
        assert len(streams[_barrier_stream_names(downstream_barrier_name)[0]]) == 1


def test_duplicate_parent_completion_does_not_dispatch_downstream_again(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process a duplicate parent event during the coordinated fan-in race."""

    completion_prefix = f"integration-duplicate-completion-{uuid4()}"
    monkeypatch.setenv("INTEGRATION_COMPLETION_BARRIER_PREFIX", completion_prefix)
    monkeypatch.setenv("INTEGRATION_COMPLETION_BARRIER_NODES", "B,C")
    monkeypatch.setenv("INTEGRATION_BARRIER_TIMEOUT_SECONDS", "30")

    with running_application_service_cluster(integration_infrastructure) as (
        orchestrators,
        worker,
    ):
        parent_barrier_name = f"duplicate-parents-{uuid4()}"
        downstream_barrier_name = f"duplicate-downstream-{uuid4()}"
        nodes: list[JsonObject] = [
            {"id": "A", "handler": "input", "dependencies": []},
            *[
                {
                    "id": node_id,
                    "handler": "integration_barrier",
                    "dependencies": ["A"],
                    "config": {
                        "barrier": {
                            "name": parent_barrier_name,
                            "participant": node_id,
                        }
                    },
                }
                for node_id in ("B", "C")
            ],
            {
                "id": "D",
                "handler": "integration_barrier",
                "dependencies": ["B", "C"],
                "config": {
                    "barrier": {
                        "name": downstream_barrier_name,
                        "participant": "D",
                    }
                },
            },
        ]
        response = api_client.post(
            "/workflow",
            json={"name": f"duplicate-completion-race-{uuid4()}", "dag": {"nodes": nodes}},
        )
        assert response.status_code == 201, response.text
        execution_id = UUID(response.json()["execution_id"])
        trigger = api_client.post(
            f"/workflow/trigger/{execution_id}",
            json={"input": {}},
        )
        assert trigger.status_code == 202, trigger.text

        fetch = _workflow_fetcher(api_client, execution_id)

        def diagnostics() -> str:
            return _service_diagnostics(orchestrators, worker)

        running = wait_for_nodes_status(
            fetch,
            str(execution_id),
            {"B": "RUNNING", "C": "RUNNING"},
            diagnostics=diagnostics,
        )
        assert node_statuses(running)["D"] == "PENDING"

        try:
            asyncio.run(
                _coordinate_duplicate_race(
                    integration_infrastructure,
                    parent_barrier_name,
                    f"{completion_prefix}:{execution_id}",
                    downstream_barrier_name,
                )
            )
        except RedisBarrierTimeout as error:
            database = inspect_database(integration_infrastructure, execution_id)
            streams = inspect_redis_streams(
                integration_infrastructure,
                (
                    *_barrier_stream_names(parent_barrier_name),
                    *_barrier_stream_names(f"{completion_prefix}:{execution_id}"),
                    *_barrier_stream_names(downstream_barrier_name),
                    "workflow.task-completions",
                ),
            )
            raise AssertionError(
                f"Duplicate completion coordination failed: {error}\n"
                f"{format_diagnostics(database, streams)}\n{diagnostics()}"
            ) from error

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

        database = inspect_database(integration_infrastructure, execution_id)
        d_logical_tasks = _node_rows(database.logical_tasks, "D", 1)
        d_task_ids = {row[0] for row in d_logical_tasks}
        d_attempts = tuple(row for row in database.task_attempts if row[1] in d_task_ids)
        assert len(d_logical_tasks) == 1
        assert len(d_attempts) == 1
        assert len(_task_outbox_rows(database, "D")) == 1

        streams = inspect_redis_streams(
            integration_infrastructure,
            (
                *_barrier_stream_names(parent_barrier_name),
                *_barrier_stream_names(f"{completion_prefix}:{execution_id}"),
                *_barrier_stream_names(downstream_barrier_name),
                "workflow.task-completions",
            ),
        )
        completion_entries = streams["workflow.task-completions"]
        b_events = [fields for _, fields in completion_entries if fields.get("node_id") == "B"]
        assert len(b_events) == 2
        assert b_events[0]["event_id"] == b_events[1]["event_id"]
        completion_arrivals = _barrier_stream_names(f"{completion_prefix}:{execution_id}")[0]
        assert len(streams[completion_arrivals]) == 3
        assert len(streams[_barrier_stream_names(downstream_barrier_name)[0]]) == 1
