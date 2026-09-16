"""Infrastructure selection and lifecycle for integration tests."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

DATABASE_URL_ENV = "DATABASE_URL"
REDIS_URL_ENV = "REDIS_URL"


@dataclass(frozen=True, slots=True)
class InfrastructureConfig:
    """Connection configuration for the integration-test application."""

    database_url: str
    redis_url: str
    provider: str


def _required_url(name: str, value: str | None, schemes: frozenset[str]) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{name} must be a non-empty URL.")

    parsed = urlparse(value)
    if parsed.scheme not in schemes or not parsed.netloc:
        expected = ", ".join(sorted(schemes))
        raise ValueError(f"{name} must use one of these URL schemes: {expected}.")
    return value


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + database_url.removeprefix("postgresql+psycopg2://")
    if database_url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+asyncpg://" + database_url.removeprefix("postgres://")
    return database_url


def external_infrastructure() -> InfrastructureConfig | None:
    """Return validated external infrastructure, or None when none is configured."""

    database_url = os.getenv(DATABASE_URL_ENV)
    redis_url = os.getenv(REDIS_URL_ENV)
    if database_url is None and redis_url is None:
        return None
    if database_url is None or redis_url is None:
        return None

    return InfrastructureConfig(
        database_url=_normalize_database_url(
            _required_url(
                DATABASE_URL_ENV,
                database_url,
                frozenset({"postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg2"}),
            )
        ),
        redis_url=_required_url(
            REDIS_URL_ENV,
            redis_url,
            frozenset({"redis", "rediss"}),
        ),
        provider="external",
    )


@contextmanager
def selected_infrastructure() -> Iterator[InfrastructureConfig]:
    """Yield external infrastructure or disposable Testcontainers infrastructure."""

    external = external_infrastructure()
    if external is not None:
        yield external
        return

    password = secrets.token_urlsafe(24)
    postgres = PostgresContainer(
        image="postgres:17",
        username="integration_test",
        password=password,
        dbname="integration_test",
    )
    redis = RedisContainer(image="redis:7.4-alpine")
    try:
        postgres.start()
        redis.start()
        yield InfrastructureConfig(
            database_url=_normalize_database_url(postgres.get_connection_url()),
            redis_url=(f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"),
            provider="testcontainers",
        )
    finally:
        redis.stop()
        postgres.stop()
