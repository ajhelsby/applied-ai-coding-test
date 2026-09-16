"""Database and Redis initialization for integration tests."""

from __future__ import annotations

import os
from pathlib import Path

import redis
from alembic.config import Config

from alembic import command
from tests.integration.fixtures.infrastructure import InfrastructureConfig

_ROOT_DIRECTORY = Path(__file__).resolve().parents[3]
_REDIS_GROUPS: tuple[tuple[str, str], ...] = (
    ("workflow.tasks", "workers"),
    ("workflow.events", "orchestrator"),
    ("workflow.task-completions", "orchestrator-completions"),
)


def configure_environment(infrastructure: InfrastructureConfig) -> None:
    """Expose selected infrastructure to application and migration code."""

    os.environ["DATABASE_URL"] = infrastructure.database_url
    os.environ["MIGRATE_DATABASE_URL"] = infrastructure.database_url
    os.environ["REDIS_URL"] = infrastructure.redis_url


def apply_database_migrations(infrastructure: InfrastructureConfig) -> None:
    """Apply all Alembic migrations to the selected PostgreSQL instance."""

    configure_environment(infrastructure)
    alembic_config = Config(str(_ROOT_DIRECTORY / "alembic.ini"))
    command.upgrade(alembic_config, "head")


def initialize_redis_streams(infrastructure: InfrastructureConfig) -> None:
    """Create the consumer groups required by the application."""

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        client.ping()
        for stream, group in _REDIS_GROUPS:
            try:
                client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
            except redis.ResponseError as error:
                if "BUSYGROUP" not in str(error):
                    raise
    finally:
        client.close()


def reset_redis_streams(infrastructure: InfrastructureConfig) -> None:
    """Remove integration streams so no messages leak between tests."""

    client = redis.Redis.from_url(infrastructure.redis_url, decode_responses=True)
    try:
        client.delete(*(stream for stream, _ in _REDIS_GROUPS))
    finally:
        client.close()
