# Event-Driven Workflow Engine

This project is a JSON-based workflow engine for validating and executing
directed acyclic graphs (DAGs) across separate API, Orchestrator, and Worker
processes.

The recommended development path uses Python 3.12 and
[uv](https://docs.astral.sh/uv/). Docker Compose is also provided for running
the complete multi-container topology.

## Documentation

- [API examples](docs/API_EXAMPLES.md) — submit, trigger, monitor, and retrieve
  a workflow with `curl`.
- [Design decisions](DESIGN.md) — readiness, fan-in coordination, persistence,
  messaging, reliability, and trade-offs.
- [Docker configuration](docker/.env.example) — environment variables used by
  the Compose deployment.
- Interactive API documentation — [http://localhost:8000/docs](http://localhost:8000/docs)
  when the API is running.

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
local development, start the infrastructure services with Docker Compose or
provide equivalent externally managed services:

```bash
export DATABASE_URL='postgresql+asyncpg://user:password@localhost:5432/applied_ai_db'
export MIGRATE_DATABASE_URL="$DATABASE_URL"
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

## Run the complete Docker Compose stack

Copy the provided environment template and start the services:

```bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up --build
```

The Compose initialization flow runs database migrations and provisions Redis
consumer groups before starting the application services. The API is available
at [http://localhost:8000](http://localhost:8000).

To stop the stack and remove its containers, networks, and database volume:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml down -v --remove-orphans
```

To exercise independent API and Worker replicas:

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml \
  up --build --scale api=3 --scale worker=4
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

Run repository formatting and lint checks with the existing pre-commit setup:

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
input and queues asynchronous processing. The API acknowledges the trigger with
`202 Accepted`; execution continues through Redis Streams and can be monitored
with the status endpoint. A successful execution reaches `completed`; any node
failure causes the workflow to reach `failed`.

The public workflow validator accepts `input`, `output`, and
`call_external_service`. The Worker registry also contains the
`integration_barrier` and `llm_service` handlers for integration/test
scenarios. The external-service and LLM handlers are deterministic mocks for
this coding test; they do not call real external services.

## API endpoint summary

| Method | Endpoint                            | Purpose                                            |
| ------ | ----------------------------------- | -------------------------------------------------- |
| `POST` | `/workflow`                         | Validate and persist a workflow definition         |
| `POST` | `/workflow/trigger/{execution_id}`  | Start a pending execution asynchronously           |
| `GET`  | `/workflows/{execution_id}`         | Read persisted workflow and node status            |
| `GET`  | `/workflows/{execution_id}/results` | Read persisted outputs after successful completion |
| `GET`  | `/health`                           | Check API health                                   |

See [API examples](docs/API_EXAMPLES.md) for request and response bodies.
