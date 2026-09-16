"""Bounded polling helpers for asynchronous workflow assertions."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping

WorkflowPayload = Mapping[str, object]
WorkflowFetcher = Callable[[], object]

_TERMINAL_FAILURE_STATUSES = frozenset({"FAILED", "CANCELLED"})


class WorkflowPollingError(AssertionError):
    """Raised when an asynchronous workflow does not reach its expected state."""


def _payload(fetch: WorkflowFetcher) -> WorkflowPayload:
    payload = fetch()
    if not isinstance(payload, Mapping):
        raise WorkflowPollingError(f"Workflow endpoint returned a non-object payload: {payload!r}")
    return payload


def _diagnostics(payload: WorkflowPayload) -> str:
    status = payload.get("status")
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return f"workflow_status={status!r}, nodes={nodes!r}"

    node_states: list[str] = []
    for node in nodes:
        if isinstance(node, Mapping):
            node_states.append(f"{node.get('node_id')!r}={node.get('status')!r}")
        else:
            node_states.append(repr(node))
    return f"workflow_status={status!r}, node_states=[{', '.join(node_states)}]"


def _poll(
    fetch: WorkflowFetcher,
    expected: Callable[[WorkflowPayload], bool],
    execution_id: str,
    expectation: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    diagnostics: Callable[[], str] | None,
) -> WorkflowPayload:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero.")

    deadline = time.monotonic() + timeout_seconds
    latest = _payload(fetch)
    while True:
        status = latest.get("status")
        if status in _TERMINAL_FAILURE_STATUSES:
            service_diagnostics = "" if diagnostics is None else f"\n{diagnostics()}"
            raise WorkflowPollingError(
                f"Workflow {execution_id} reached unexpected terminal state {status!r} "
                f"while waiting for {expectation}. {_diagnostics(latest)}{service_diagnostics}"
            )
        if expected(latest):
            return latest
        if time.monotonic() >= deadline:
            service_diagnostics = "" if diagnostics is None else f"\n{diagnostics()}"
            raise WorkflowPollingError(
                f"Timed out after {timeout_seconds:.1f}s waiting for {expectation} "
                f"for workflow {execution_id}. {_diagnostics(latest)}{service_diagnostics}"
            )
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))
        latest = _payload(fetch)


def wait_for_workflow_status(
    fetch: WorkflowFetcher,
    execution_id: str,
    expected_status: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.1,
    diagnostics: Callable[[], str] | None = None,
) -> WorkflowPayload:
    """Wait for a workflow execution to reach a specific status."""

    return _poll(
        fetch,
        lambda payload: payload.get("status") == expected_status,
        execution_id,
        f"workflow status {expected_status!r}",
        timeout_seconds,
        poll_interval_seconds,
        diagnostics,
    )


def wait_for_node_status(
    fetch: WorkflowFetcher,
    execution_id: str,
    node_id: str,
    expected_status: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.1,
    diagnostics: Callable[[], str] | None = None,
) -> WorkflowPayload:
    """Wait for one node to reach a specific status."""

    def node_is_ready(payload: WorkflowPayload) -> bool:
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            return False
        return any(
            isinstance(node, Mapping)
            and node.get("node_id") == node_id
            and node.get("status") == expected_status
            for node in nodes
        )

    return _poll(
        fetch,
        node_is_ready,
        execution_id,
        f"node {node_id!r} status {expected_status!r}",
        timeout_seconds,
        poll_interval_seconds,
        diagnostics,
    )
