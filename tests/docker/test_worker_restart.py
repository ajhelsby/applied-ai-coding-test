"""Worker restart and recovery coverage for the Docker Compose deployment."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from tests.docker.helpers.api import DockerApiClient
from tests.docker.helpers.compose import ComposeEnvironment
from tests.docker.helpers.polling import (
    node_statuses,
    wait_for_node_status,
    wait_for_workflow_status,
)
from tests.docker.helpers.readiness import wait_for_compose_readiness
from tests.docker.helpers.workflows import diamond_workflow_nodes


def test_worker_restart_recovers_an_active_workflow(
    compose_environment_factory: Callable[..., ComposeEnvironment],
) -> None:
    """Restart one Worker while work is active and complete the workflow afterward."""

    compose = compose_environment_factory(api_replicas=1, worker_replicas=2)
    with DockerApiClient(compose.api_url()) as client:
        execution_id = client.submit_workflow(diamond_workflow_nodes(latency_ms=3_000))
        client.trigger_workflow(execution_id, input_data={"value": "worker-recovery"})

        active = wait_for_node_status(client, execution_id, "B", "RUNNING")
        assert node_statuses(active)["D"] == "PENDING"

        compose.restart_container("worker", index=0)
        wait_for_compose_readiness(compose)

        completed = wait_for_workflow_status(client, execution_id, "COMPLETED")
        assert node_statuses(completed) == {
            "A": "COMPLETED",
            "B": "COMPLETED",
            "C": "COMPLETED",
            "D": "COMPLETED",
        }

        results = client.get_workflow_results(execution_id)
        result_items = results.get("results")
        assert isinstance(result_items, list)
        result_node_ids = [
            result["node_id"]
            for result in result_items
            if isinstance(result, Mapping) and isinstance(result.get("node_id"), str)
        ]
        assert len(result_node_ids) == 4
        assert set(result_node_ids) == {"A", "B", "C", "D"}
