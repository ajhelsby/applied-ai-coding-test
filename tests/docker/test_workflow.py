"""End-to-end workflow coverage for the Docker Compose deployment."""

from __future__ import annotations

from collections.abc import Mapping

from tests.docker.helpers.api import DockerApiClient
from tests.docker.helpers.polling import node_statuses, wait_for_workflow_status
from tests.docker.helpers.workflows import diamond_workflow_nodes


def test_diamond_workflow_completes_through_the_compose_stack(
    api_client: DockerApiClient,
) -> None:
    """Submit, execute, and retrieve a fan-out/fan-in workflow over HTTP."""

    execution_id = api_client.submit_workflow(diamond_workflow_nodes())
    trigger = api_client.trigger_workflow(
        execution_id,
        input_data={"value": "compose-diamond"},
    )

    assert trigger["execution_id"] == str(execution_id)
    assert trigger["status"] == "running"

    running = api_client.get_workflow_status(execution_id)
    assert running["status"] == "RUNNING"

    completed = wait_for_workflow_status(api_client, execution_id, "COMPLETED")
    assert node_statuses(completed) == {
        "A": "COMPLETED",
        "B": "COMPLETED",
        "C": "COMPLETED",
        "D": "COMPLETED",
    }

    results = api_client.get_workflow_results(execution_id)
    assert results["status"] == "COMPLETED"
    result_items = results.get("results")
    assert isinstance(result_items, list)
    result_by_node = {
        result["node_id"]: result
        for result in result_items
        if isinstance(result, Mapping) and isinstance(result.get("node_id"), str)
    }
    assert set(result_by_node) == {"A", "B", "C", "D"}
    d_result = result_by_node.get("D")
    assert isinstance(d_result, Mapping)
    d_output = d_result.get("output_data")
    assert isinstance(d_output, Mapping)
    d_input = d_output.get("input")
    assert isinstance(d_input, Mapping)
    assert d_input.get("branches") == {
        "b": "https://docker-branch-b.example/compose-diamond",
        "c": "https://docker-branch-c.example/compose-diamond",
    }
