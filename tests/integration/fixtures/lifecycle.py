"""Application and service-process lifecycle helpers for integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from tests.integration.fixtures.infrastructure import InfrastructureConfig

_ROOT_DIRECTORY = Path(__file__).resolve().parents[3]
_SHUTDOWN_TIMEOUT_SECONDS = 10.0


class ServiceProcessError(RuntimeError):
    """Raised when an integration service exits unexpectedly."""


class ServiceProcess:
    """Manage one application service subprocess and its captured output."""

    def __init__(self, name: str, process: subprocess.Popen[bytes], log_file: BinaryIO) -> None:
        self.name = name
        self.process = process
        self._log_file = log_file

    def ensure_running(self) -> None:
        """Raise with captured output if the service exited during startup."""

        return_code = self.process.poll()
        if return_code is not None:
            raise ServiceProcessError(
                f"{self.name} exited during startup with code {return_code}.\n{self.output()}"
            )

    def output(self) -> str:
        """Return all captured service output."""

        self._log_file.seek(0)
        return self._log_file.read().decode("utf-8", errors="replace")

    def stop(self) -> None:
        """Stop the service and retain output for diagnostics."""

        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        self._log_file.close()


def _service_environment(infrastructure: InfrastructureConfig) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": infrastructure.database_url,
            "MIGRATE_DATABASE_URL": infrastructure.database_url,
            "REDIS_URL": infrastructure.redis_url,
            "PYTHONPATH": str(_ROOT_DIRECTORY),
            "OUTBOX_POLL_INTERVAL_SECONDS": "0.05",
            "MOCK_LLM_LATENCY_MS": "0",
            "MOCK_LLM_FORCE_FAIL": "false",
            "MOCK_LLM_FAILURE_RATE": "0",
            "MOCK_EXTERNAL_SERVICE_LATENCY_MS": "0",
            "MOCK_EXTERNAL_SERVICE_FORCE_FAIL": "false",
            "MOCK_EXTERNAL_SERVICE_FAILURE_RATE": "0",
        }
    )
    consumer_suffix = uuid.uuid4().hex
    environment["ORCHESTRATOR_CONSUMER_NAME"] = f"integration-orchestrator-{consumer_suffix}"
    environment["WORKER_CONSUMER_NAME"] = f"integration-worker-{consumer_suffix}"
    return environment


def _start_service(
    name: str,
    module: str,
    environment: dict[str, str],
) -> ServiceProcess:
    log_file = tempfile.TemporaryFile()
    process = subprocess.Popen(
        [sys.executable, "-m", module],
        cwd=_ROOT_DIRECTORY,
        env=environment,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    service = ServiceProcess(name, process, log_file)
    service.ensure_running()
    return service


def _orchestrator_environment(
    environment: dict[str, str],
    index: int,
) -> dict[str, str]:
    orchestrator_environment = environment.copy()
    suffix = uuid.uuid4().hex
    orchestrator_environment["ORCHESTRATOR_CONSUMER_NAME"] = (
        f"integration-orchestrator-{index}-{suffix}"
    )
    return orchestrator_environment


@contextmanager
def running_application_service_cluster(
    infrastructure: InfrastructureConfig,
    *,
    orchestrator_count: int = 2,
) -> Iterator[tuple[tuple[ServiceProcess, ...], ServiceProcess]]:
    """Run one worker and multiple independent Orchestrator processes."""

    if orchestrator_count < 1:
        raise ValueError("orchestrator_count must be at least one.")

    environment = _service_environment(infrastructure)
    orchestrators: list[ServiceProcess] = []
    worker: ServiceProcess | None = None
    try:
        for index in range(orchestrator_count):
            orchestrators.append(
                _start_service(
                    f"orchestrator-{index + 1}",
                    "app.orchestrator.main",
                    _orchestrator_environment(environment, index + 1),
                )
            )
        worker = _start_service("worker", "app.worker.main", environment)
        yield tuple(orchestrators), worker
    finally:
        if worker is not None:
            worker.stop()
        for orchestrator in reversed(orchestrators):
            orchestrator.stop()


@contextmanager
def running_application_services(
    infrastructure: InfrastructureConfig,
) -> Iterator[tuple[ServiceProcess, ServiceProcess]]:
    """Run the Orchestrator and Worker until the test scope exits."""

    environment = _service_environment(infrastructure)
    orchestrator: ServiceProcess | None = None
    worker: ServiceProcess | None = None
    try:
        orchestrator = _start_service(
            "orchestrator",
            "app.orchestrator.main",
            environment,
        )
        worker = _start_service("worker", "app.worker.main", environment)
        yield orchestrator, worker
    finally:
        if worker is not None:
            worker.stop()
        if orchestrator is not None:
            orchestrator.stop()
