"""Scaled Docker Compose topology coverage."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from tests.docker.helpers.api import DockerApiClient
from tests.docker.helpers.compose import ComposeEnvironment
from tests.docker.helpers.polling import node_statuses, wait_for_workflow_status
from tests.docker.helpers.workflows import diamond_workflow_nodes


def test_scaled_compose_topology_executes_a_workflow(
    compose_environment_factory: Callable[..., ComposeEnvironment],
) -> None:
    """Run the workflow with multiple API and Worker replicas."""

    compose = compose_environment_factory(api_replicas=3, worker_replicas=4)
    assert compose.api_replicas == 3
    assert compose.worker_replicas == 4

    with DockerApiClient(compose.api_url()) as client:
        assert client.health()["status"] == "healthy"
        execution_id = client.submit_workflow(diamond_workflow_nodes(latency_ms=250))
        trigger = client.trigger_workflow(
            execution_id,
            input_data={"value": "scaled-compose"},
        )
        assert trigger["execution_id"] == str(execution_id)

        completed = wait_for_workflow_status(client, execution_id, "COMPLETED")
        assert node_statuses(completed) == {
            "A": "COMPLETED",
            "B": "COMPLETED",
            "C": "COMPLETED",
            "D": "COMPLETED",
        }

        results = client.get_workflow_results(execution_id)
        assert results["status"] == "COMPLETED"
        result_items = results.get("results")
        assert isinstance(result_items, list)
        result_by_node = {
            result["node_id"]: result
            for result in result_items
            if isinstance(result, Mapping) and isinstance(result.get("node_id"), str)
        }
        assert set(result_by_node) == {"A", "B", "C", "D"}
