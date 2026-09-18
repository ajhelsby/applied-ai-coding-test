"""Application-container restart and persistence coverage."""

from __future__ import annotations

from collections.abc import Callable

from tests.docker.helpers.api import DockerApiClient
from tests.docker.helpers.compose import ComposeEnvironment
from tests.docker.helpers.polling import (
    node_statuses,
    wait_for_node_status,
    wait_for_workflow_status,
)
from tests.docker.helpers.readiness import wait_for_compose_readiness
from tests.docker.helpers.workflows import diamond_workflow_nodes


def test_api_restart_does_not_interrupt_background_execution(
    compose_environment_factory: Callable[..., ComposeEnvironment],
) -> None:
    """Restart an API container while Orchestrator and Workers continue processing."""

    compose = compose_environment_factory()
    with DockerApiClient(compose.api_url()) as client:
        execution_id = client.submit_workflow(diamond_workflow_nodes(latency_ms=1_500))
        client.trigger_workflow(execution_id, input_data={"value": "api-restart"})
        wait_for_node_status(client, execution_id, "B", "RUNNING")

        compose.restart_container("api")
        wait_for_compose_readiness(compose)

        with DockerApiClient(compose.api_url()) as restarted_client:
            status = restarted_client.get_workflow_status(execution_id)
            assert status["execution_id"] == str(execution_id)
            completed = wait_for_workflow_status(restarted_client, execution_id, "COMPLETED")
            assert node_statuses(completed) == {
                "A": "COMPLETED",
                "B": "COMPLETED",
                "C": "COMPLETED",
                "D": "COMPLETED",
            }


def test_workflow_state_survives_application_container_restarts(
    compose_environment_factory: Callable[..., ComposeEnvironment],
) -> None:
    """Keep PostgreSQL intact while restarting all application service containers."""

    compose = compose_environment_factory()
    with DockerApiClient(compose.api_url()) as client:
        execution_id = client.submit_workflow(diamond_workflow_nodes(latency_ms=250))
        client.trigger_workflow(execution_id, input_data={"value": "durable-state"})
        wait_for_workflow_status(client, execution_id, "COMPLETED")

        compose.restart_container("api")
        compose.restart_container("orchestrator")
        compose.restart_container("worker")
        wait_for_compose_readiness(compose)

        with DockerApiClient(compose.api_url()) as restarted_client:
            status = restarted_client.get_workflow_status(execution_id)
            results = restarted_client.get_workflow_results(execution_id)
            assert status["execution_id"] == str(execution_id)
            assert status["status"] == "COMPLETED"
            assert results["execution_id"] == str(execution_id)
            assert results["status"] == "COMPLETED"
            assert isinstance(results.get("results"), list)
