"""Pytest fixtures for Docker Compose topology tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping

import pytest

from tests.docker.helpers.api import DockerApiClient
from tests.docker.helpers.compose import (
    ComposeCommandError,
    ComposeEnvironment,
    running_compose_environment,
)
from tests.docker.helpers.readiness import wait_for_compose_readiness

ComposeEnvironmentFactory = Callable[..., ComposeEnvironment]


@pytest.fixture
def compose_environment() -> Iterator[ComposeEnvironment]:
    """Run the default Docker Compose topology for one test."""

    with running_compose_environment() as compose:
        yield compose


@pytest.fixture
def compose_environment_factory() -> Iterator[ComposeEnvironmentFactory]:
    """Create isolated Compose environments with requested replica counts."""

    environments: list[ComposeEnvironment] = []

    def factory(
        *,
        environment: Mapping[str, str] | None = None,
        api_replicas: int = 1,
        worker_replicas: int = 1,
    ) -> ComposeEnvironment:
        compose = ComposeEnvironment(
            environment=environment,
            api_replicas=api_replicas,
            worker_replicas=worker_replicas,
        )
        environments.append(compose)
        try:
            compose.start()
            wait_for_compose_readiness(compose)
        except ComposeCommandError as error:
            raise RuntimeError(
                f"Docker Compose environment failed.\n{compose.diagnostics()}"
            ) from error
        return compose

    yield factory

    for compose in reversed(environments):
        compose.stop()


@pytest.fixture
def api_client(compose_environment: ComposeEnvironment) -> Iterator[DockerApiClient]:
    """Create an HTTP client connected to the deployed API."""

    with DockerApiClient(compose_environment.api_url()) as client:
        yield client
