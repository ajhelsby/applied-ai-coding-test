"""Bounded readiness polling for Docker Compose services."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping

from tests.docker.helpers.compose import ComposeCommandError, ComposeEnvironment


class ComposeReadinessError(RuntimeError):
    """Raised when the Compose topology does not become ready in time."""


def _service_statuses(compose: ComposeEnvironment) -> dict[str, list[Mapping[str, object]]]:
    result = compose.run("ps", "--all", "--format", "json", check=False)
    if result.returncode != 0:
        return {}

    try:
        decoded: object = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        records = []
        for line in result.stdout.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                return {}
    else:
        if isinstance(decoded, list):
            records = decoded
        elif isinstance(decoded, Mapping):
            records = [decoded]
        else:
            return {}

    statuses: dict[str, list[Mapping[str, object]]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        service = record.get("Service")
        if isinstance(service, str):
            statuses.setdefault(service, []).append(record)
    return statuses


def _api_is_ready(compose: ComposeEnvironment) -> bool:
    try:
        port_result = compose.run("port", "api", "8000")
        host_port = port_result.stdout.strip().splitlines()[0].rsplit(":", 1)[-1]
        with urllib.request.urlopen(f"http://127.0.0.1:{host_port}/health", timeout=2) as response:
            return response.status == 200
    except (
        ComposeCommandError,
        ComposeReadinessError,
        IndexError,
        OSError,
        ValueError,
        urllib.error.URLError,
    ):
        return False


def _service_is_healthy(
    statuses: Mapping[str, list[Mapping[str, object]]],
    service: str,
    replicas: int,
) -> bool:
    records = statuses.get(service, [])
    if len(records) < replicas:
        return False
    return all(
        record.get("State") == "running" and record.get("Health") == "healthy"
        for record in records
    )


def wait_for_compose_readiness(
    compose: ComposeEnvironment,
    *,
    timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 2.0,
) -> None:
    """Wait until infrastructure, application services, and the API are ready."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero.")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        statuses = _service_statuses(compose)
        ready = (
            _service_is_healthy(statuses, "postgres", 1)
            and _service_is_healthy(statuses, "redis", 1)
            and _service_is_healthy(statuses, "orchestrator", 1)
            and _service_is_healthy(statuses, "worker", compose.worker_replicas)
            and _service_is_healthy(statuses, "api", compose.api_replicas)
            and _api_is_ready(compose)
        )
        if ready:
            return
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    raise ComposeReadinessError(
        f"Docker Compose environment did not become ready within {timeout_seconds:.1f}s.\n"
        f"{compose.diagnostics()}"
    )
