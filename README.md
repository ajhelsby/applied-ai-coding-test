# Event-Driven Workflow Engine

This project is a JSON-based workflow engine for validating and executing
directed acyclic graphs (DAGs) across separate API, Orchestrator, and Worker
processes.

The recommended development path uses Python 3.12 and
[uv](https://docs.astral.sh/uv/). Docker Compose runs the complete
multi-container topology.

## Documentation

- [API examples](docs/API_EXAMPLES.md) — submit, trigger, monitor, and retrieve
  a workflow with `curl`.
- [Design decisions](DESIGN.md) — readiness, fan-in coordination, persistence,
  messaging, reliability, and trade-offs.
- [Docker configuration](docker/.env.example) — environment variables used by
  the Compose deployment.
- Interactive API documentation — use the host port reported by
  `docker compose port api 8000`.

## Architecture overview

```mermaid
flowchart LR
    Client --> API[FastAPI API]
    API -->|workflow state and outbox| DB[(PostgreSQL)]
    DB -->|published outbox messages| Redis[(Redis Streams)]
    Redis --> Orch[Orchestrator]
    Orch -->|task messages| Redis
    Redis --> Worker[Worker]
    Worker -->|completion events| Redis
    Orch -->|node outputs and state| DB
```

PostgreSQL is the durable source of truth for workflow definitions, execution
state, node outputs, retry state, task-processing state, and outbox records.
Redis Streams provides asynchronous transport between processes and is not
canonical state storage.

The API accepts and validates workflow definitions and exposes read-only
status/results endpoints. The Orchestrator evaluates dependencies, dispatches
ready nodes, processes completion events, and finalizes executions. Workers
consume tasks, run registered handlers, and publish completion events.

## Quick start with uv

### Prerequisites

- Python 3.12
- `uv`
- Docker, for PostgreSQL and Redis during integration tests
- Docker Compose, for the full deployed topology

Install dependencies:

```bash
uv sync
```

### Run the API locally

The API requires PostgreSQL and Redis connection URLs in the environment. For
local development, use externally managed services or run the infrastructure
services with Docker Compose and connect through `localhost`:

```bash
export DATABASE_URL='postgresql+asyncpg://user:password@localhost:5432/applied_ai_db'
export MIGRATE_DATABASE_URL='postgresql+psycopg2://user:password@localhost:5432/applied_ai_db'
export REDIS_URL='redis://localhost:6379/0'
```

Apply the database migration and initialize Redis Streams:

```bash
uv run alembic upgrade head
uv run python scripts/init-redis-streams.py
```

Run the API, Orchestrator, and Worker in separate terminals:

```bash
uv run uvicorn app.api.main:app --host 0.0.0.0 --port 8000
uv run python -m app.orchestrator.main
uv run python -m app.worker.main
```

Then follow the [API examples](docs/API_EXAMPLES.md).

## Docker Compose runtime

Copy the provided environment template:

```bash
cp docker/.env.example docker/.env
```

Start the complete stack:

```bash
docker compose --env-file docker/.env \
  -f docker/docker-compose.yml up --build --force-recreate
```

The Compose services must use `postgres` as the database hostname because that
is the PostgreSQL service name on the Compose network. `DATABASE_URL` and
`MIGRATE_DATABASE_URL` in `docker/.env` must not use `localhost`.

The API uses the first available host port in the `8000-8002` range. Find the
assigned port with:

```bash
docker compose --env-file docker/.env \
  -f docker/docker-compose.yml port api 8000
```

Open `/docs` on the returned port, for example
`http://localhost:8002/docs`. Check readiness with:

```bash
curl -fsS http://localhost:8002/health
```

### Connect with DBeaver

PostgreSQL is published to host port `5433` by default so it does not
conflict with another local PostgreSQL server. Use these DBeaver settings:

| Setting  | Value                                  |
| -------- | -------------------------------------- |
| Host     | `localhost`                            |
| Port     | `5433`                                 |
| Database | `applied_ai_db`                        |
| Username | `applied_ai_user`                      |
| Password | `POSTGRES_PASSWORD` from `docker/.env` |

If port `5433` is already in use, set `POSTGRES_HOST_PORT` in `docker/.env` to
another free host port and use that port in DBeaver. Restart the Compose stack
after changing it.

If the stack was started with an old environment, refresh containers without
removing database data:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml down
docker compose --env-file docker/.env \
  -f docker/docker-compose.yml up --build --force-recreate
```

Do not use `down -v` unless the local database is disposable.

### PostgreSQL version and data persistence

The Compose environment uses PostgreSQL **16.10**. PostgreSQL data is stored
in the named `postgres_data` volume and is preserved by normal `up` and
`down` commands. Startup never removes or recreates this volume.

The existing development volume was initialized by PostgreSQL 16 and is
compatible with this configuration. PostgreSQL major versions are not
data-directory compatible. A future upgrade to PostgreSQL 17 or another major
version requires a verified logical backup and restore, or an approved
`pg_upgrade` process. Never start a newer server directly against an older
major-version data directory.

For a major-version upgrade, keep the old volume until the restored database,
migrations, and application behavior have been verified. An upgrade must not
be performed by changing only the image tag in Compose.

### Scaling the application services

```bash
docker compose --env-file docker/.env \
  -f docker/docker-compose.yml up --build --scale api=3 --scale worker=4
```

### Stopping and resetting local data

Stop the stack while preserving the database volume:

```bash
docker compose --env-file docker/.env \
  -f docker/docker-compose.yml down --remove-orphans
```

For a disposable local database only, remove the volume explicitly:

```bash
docker compose --env-file docker/.env \
  -f docker/docker-compose.yml down -v --remove-orphans
```

## Testing

Run the fast tests without external infrastructure:

```bash
uv run pytest -q tests/unit
```

Run integration tests:

```bash
uv run pytest -q tests/integration
```

Integration tests use externally supplied PostgreSQL and Redis when both
`DATABASE_URL` and `REDIS_URL` are set. When neither is set, they start
disposable PostgreSQL and Redis containers automatically. Docker must be
running for this fallback.

Run the Docker end-to-end suite against the Compose deployment:

```bash
uv run pytest -q tests/docker
```

For a lightweight Compose health and documentation check:

```bash
bash tests/docker/verify_compose.sh
```

Run repository formatting and lint checks:

```bash
uv run pre-commit run --all-files
```

## Workflow model

A submitted workflow contains a name and a `dag.nodes` list. Each node has an
identifier, handler, dependency identifiers, and handler configuration.
Definitions are validated for required fields, unique and valid node IDs,
supported handlers, valid handler configuration, known dependencies, and
cycles before they are persisted.

Submission creates a pending execution. A separate trigger request stores JSON
input and queues asynchronous processing. The API acknowledges the trigger
with `202 Accepted`; execution continues through Redis Streams and can be
monitored with the status endpoint. A successful execution reaches `COMPLETED`;
any node failure causes the workflow to reach `FAILED`.

The public workflow validator accepts `input`, `output`,
`call_external_service`, and `llm_service`. The Worker registry also contains
the `integration_barrier` handler for integration/test scenarios. The
external-service and LLM handlers are deterministic mocks for this coding test;
they do not call real external services. LLM nodes require a non-empty string
`config.prompt`, which may contain templates referencing completed dependency
outputs.

## API endpoint summary

| Method | Endpoint                            | Purpose                                            |
| ------ | ----------------------------------- | -------------------------------------------------- |
| `POST` | `/workflow`                         | Validate and persist a workflow definition         |
| `POST` | `/workflow/trigger/{execution_id}`  | Start a pending execution asynchronously           |
| `GET`  | `/workflows/{execution_id}`         | Read persisted workflow and node status            |
| `GET`  | `/workflows/{execution_id}/results` | Read persisted outputs after successful completion |
| `GET`  | `/health`                           | Check API health                                   |

See [API examples](docs/API_EXAMPLES.md) for request and response bodies.
