"""Bounded polling helpers for Docker workflow assertions."""

from __future__ import annotations

import time
from collections.abc import Mapping
from uuid import UUID

from tests.docker.helpers.api import DockerApiClient, JsonObject


class DockerWorkflowPollingError(AssertionError):
    """Raised when a deployed workflow does not reach the expected state."""


def wait_for_workflow_status(
    client: DockerApiClient,
    execution_id: UUID,
    expected_status: str,
    *,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 0.2,
) -> JsonObject:
    """Wait for a workflow status through the public API."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero.")

    deadline = time.monotonic() + timeout_seconds
    latest = client.get_workflow_status(execution_id)
    while True:
        status = latest.get("status")
        if status in {"FAILED", "CANCELLED"}:
            raise DockerWorkflowPollingError(
                f"Workflow {execution_id} reached terminal status {status!r}: {latest!r}"
            )
        if status == expected_status:
            return latest
        if time.monotonic() >= deadline:
            raise DockerWorkflowPollingError(
                f"Timed out after {timeout_seconds:.1f}s waiting for {expected_status!r} "
                f"for workflow {execution_id}: {latest!r}"
            )
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))
        latest = client.get_workflow_status(execution_id)


def node_statuses(payload: Mapping[str, object]) -> dict[str, str]:
    """Extract node statuses from a workflow status response."""

    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        raise DockerWorkflowPollingError(f"Workflow response has invalid nodes: {payload!r}")

    statuses: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, Mapping):
            raise DockerWorkflowPollingError(f"Workflow response has an invalid node: {node!r}")
        node_id = node.get("node_id")
        status = node.get("status")
        if not isinstance(node_id, str) or not isinstance(status, str):
            raise DockerWorkflowPollingError(f"Workflow response has an invalid node: {node!r}")
        statuses[node_id] = status
    return statuses


def wait_for_node_status(
    client: DockerApiClient,
    execution_id: UUID,
    node_id: str,
    expected_status: str,
    *,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 0.2,
) -> JsonObject:
    """Wait for one node to reach a status through the public API."""

    deadline = time.monotonic() + timeout_seconds
    latest = client.get_workflow_status(execution_id)
    while True:
        if node_statuses(latest).get(node_id) == expected_status:
            return latest
        if latest.get("status") in {"FAILED", "CANCELLED"}:
            raise DockerWorkflowPollingError(
                f"Workflow {execution_id} reached terminal status {latest.get('status')!r}: "
                f"{latest!r}"
            )
        if time.monotonic() >= deadline:
            raise DockerWorkflowPollingError(
                f"Timed out after {timeout_seconds:.1f}s waiting for node {node_id!r} "
                f"status {expected_status!r} for workflow {execution_id}: {latest!r}"
            )
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))
        latest = client.get_workflow_status(execution_id)
