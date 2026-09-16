"""Shared pytest fixtures for real PostgreSQL and Redis integration tests."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg2
import pytest
from fastapi.testclient import TestClient

from tests.integration.fixtures.infrastructure import (
    InfrastructureConfig,
    selected_infrastructure,
)
from tests.integration.fixtures.initialization import (
    apply_database_migrations,
    configure_environment,
    initialize_redis_streams,
    reset_redis_streams,
)
from tests.integration.fixtures.lifecycle import (
    ServiceProcess,
    running_application_services,
)


@pytest.fixture(scope="session")
def integration_infrastructure() -> Iterator[InfrastructureConfig]:
    """Select, initialize, and expose shared integration infrastructure."""

    with selected_infrastructure() as infrastructure:
        configure_environment(infrastructure)
        apply_database_migrations(infrastructure)
        reset_redis_streams(infrastructure)
        initialize_redis_streams(infrastructure)
        yield infrastructure


def _cleanup_database(infrastructure: InfrastructureConfig) -> None:
    database_url = infrastructure.database_url.replace("+asyncpg", "")
    connection = psycopg2.connect(database_url)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            for table in (
                "task_retry_dispatches",
                "task_attempts",
                "logical_tasks",
                "task_processing",
                "outbox_events",
                "node_executions",
                "workflow_executions",
                "workflows",
            ):
                cursor.execute(f"DELETE FROM {table}")
    finally:
        connection.close()


@pytest.fixture
def clean_test_data(integration_infrastructure: InfrastructureConfig) -> Iterator[None]:
    """Keep PostgreSQL application state isolated between tests."""

    _cleanup_database(integration_infrastructure)
    reset_redis_streams(integration_infrastructure)
    initialize_redis_streams(integration_infrastructure)
    try:
        yield
    finally:
        _cleanup_database(integration_infrastructure)
        reset_redis_streams(integration_infrastructure)


@pytest.fixture
def api_client(
    integration_infrastructure: InfrastructureConfig,
    clean_test_data: None,
) -> Iterator[TestClient]:
    """Create a FastAPI client after application configuration is available."""

    del integration_infrastructure, clean_test_data
    from app.api.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def application_services(
    integration_infrastructure: InfrastructureConfig,
    clean_test_data: None,
) -> Iterator[tuple[ServiceProcess, ServiceProcess]]:
    """Run the real Orchestrator and Worker for one integration test."""

    del clean_test_data
    with running_application_services(integration_infrastructure) as services:
        yield services
