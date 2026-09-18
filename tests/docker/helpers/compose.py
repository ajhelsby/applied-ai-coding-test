"""Docker Compose lifecycle helpers for topology tests."""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

_ROOT_DIRECTORY = Path(__file__).resolve().parents[3]
_COMPOSE_FILE = _ROOT_DIRECTORY / "docker" / "docker-compose.yml"
_DEFAULT_ENVIRONMENT = {
    "DATABASE_URL": (
        "postgresql+asyncpg://applied_ai_user:applied_ai_password@postgres:5432/applied_ai_db"
    ),
    "MIGRATE_DATABASE_URL": (
        "postgresql+psycopg2://applied_ai_user:applied_ai_password@postgres:5432/applied_ai_db"
    ),
    "REDIS_URL": "redis://redis:6379/0",
    "LOG_LEVEL": "INFO",
    "POSTGRES_DB": "applied_ai_db",
    "POSTGRES_USER": "applied_ai_user",
    "POSTGRES_PASSWORD": "applied_ai_password",
    "MOCK_LLM_SEED": "0",
    "MOCK_LLM_LATENCY_MS": "10",
    "MOCK_LLM_FORCE_FAIL": "false",
    "MOCK_LLM_FAILURE_RATE": "0.0",
    "MOCK_LLM_FAILURE_MESSAGE": "Mock LLM service failure.",
}


class ComposeCommandError(RuntimeError):
    """Raised when a Docker Compose command fails."""


class ComposeEnvironment:
    """Manage one isolated Docker Compose project."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        api_replicas: int = 1,
        worker_replicas: int = 1,
    ) -> None:
        if api_replicas < 1:
            raise ValueError("api_replicas must be at least one.")
        if worker_replicas < 1:
            raise ValueError("worker_replicas must be at least one.")

        self.project_name = f"workflow-docker-test-{uuid.uuid4().hex[:12]}"
        self.api_replicas = api_replicas
        self.worker_replicas = worker_replicas
        self._environment = os.environ.copy()
        self._environment.update(_DEFAULT_ENVIRONMENT)
        if environment is not None:
            self._environment.update(environment)

    @property
    def command_prefix(self) -> list[str]:
        """Return the common Docker Compose command arguments."""

        return [
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "--file",
            str(_COMPOSE_FILE),
        ]

    def run(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a Docker Compose command and return its captured output."""

        result = subprocess.run(
            [*self.command_prefix, *arguments],
            cwd=_ROOT_DIRECTORY,
            env=self._environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise ComposeCommandError(
                f"Docker Compose command failed with exit code {result.returncode}: "
                f"{' '.join(arguments)}\n{result.stdout}\n{result.stderr}"
            )
        return result

    def start(self) -> None:
        """Build and start the configured Compose topology."""

        self.run(
            "up",
            "--build",
            "--detach",
            "--scale",
            f"api={self.api_replicas}",
            "--scale",
            f"worker={self.worker_replicas}",
        )

    def stop(self) -> None:
        """Stop the project and remove its volumes and orphan containers."""

        try:
            self.run("down", "--volumes", "--remove-orphans", check=False)
        except FileNotFoundError:
            return

    def api_url(self) -> str:
        """Return the host URL for one published API replica."""

        result = self.run("port", "api", "8000")
        host_port = result.stdout.strip().splitlines()[0].rsplit(":", 1)[-1]
        return f"http://127.0.0.1:{host_port}"

    def container_ids(self, service: str) -> list[str]:
        """Return container IDs for a Compose service."""

        result = self.run("ps", "--all", "--quiet", service)
        return [container_id for container_id in result.stdout.splitlines() if container_id]

    def restart_container(self, service: str, *, index: int = 0) -> None:
        """Restart one selected container belonging to a Compose service."""

        container_ids = self.container_ids(service)
        if index < 0 or index >= len(container_ids):
            raise ComposeCommandError(
                f"Compose service {service!r} has no container at index {index}."
            )
        result = subprocess.run(
            ["docker", "restart", container_ids[index]],
            cwd=_ROOT_DIRECTORY,
            env=self._environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComposeCommandError(
                f"Docker container restart failed with exit code {result.returncode}:\n"
                f"{result.stdout}\n{result.stderr}"
            )

    def diagnostics(self) -> str:
        """Collect Compose status and service logs for failure reporting."""

        status = self.run("ps", check=False)
        logs = self.run("logs", "--no-color", check=False)
        return (
            "docker compose ps:\n"
            f"{status.stdout}\n{status.stderr}\n"
            "docker compose logs:\n"
            f"{logs.stdout}\n{logs.stderr}"
        )


@contextmanager
def running_compose_environment(
    *,
    environment: Mapping[str, str] | None = None,
    api_replicas: int = 1,
    worker_replicas: int = 1,
) -> Iterator[ComposeEnvironment]:
    """Start an isolated Compose environment and always clean it up."""

    from tests.docker.helpers.readiness import wait_for_compose_readiness

    compose = ComposeEnvironment(
        environment=environment,
        api_replicas=api_replicas,
        worker_replicas=worker_replicas,
    )
    try:
        compose.start()
        wait_for_compose_readiness(compose)
        yield compose
    except ComposeCommandError as error:
        raise RuntimeError(
            f"Docker Compose environment failed.\n{compose.diagnostics()}"
        ) from error
    finally:
        compose.stop()
