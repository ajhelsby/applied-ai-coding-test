# applied-ai-coding-test

## Requirements

- Python 3.12
- Docker and Docker Compose
- Node.js (required for running all `pre-commit` hooks, including JS-based hooks)

## Integration tests

Run the integration suite with:

```bash
uv run pytest tests/integration
```

The suite uses externally configured PostgreSQL and Redis when both `DATABASE_URL` and
`REDIS_URL` are set. When neither is configured, it starts disposable PostgreSQL and Redis
Testcontainers automatically. Docker must be running for the local fallback mode.

## Docker runtime

1. Copy Docker environment defaults:
   ```bash
   cp docker/.env.example docker/.env
   ```
2. Start the full local stack:
   ```bash
   docker compose --env-file docker/.env -f docker/docker-compose.yml up --build
   ```
3. API docs:
   - http://localhost:8000/docs

## Workflow execution endpoints

- `GET /workflows/{execution_id}` returns current persisted execution and node statuses.
- `GET /workflows/{execution_id}/results` returns final aggregated node outputs when execution has completed successfully.
  - Assumption/invariant: if any node execution fails, the workflow execution is marked `FAILED`; therefore `COMPLETED` represents successful completion.
  - Defensive behavior: if persisted state is inconsistent (execution is `COMPLETED` but any node is `FAILED`), the endpoint returns `results: null` with an inconsistency message.
  - `404` if the execution does not exist.
  - `200` with `results: null` for `PENDING` or `RUNNING` executions.
  - `200` with `results: null` for `FAILED` executions.
  - `200` with `results` for `COMPLETED` executions, with each result item preserving node-level provenance (`node_id`) and output payload (`output_data`).

## Mock LLM service configuration

### Task retry configuration

The Orchestrator reads retry policy settings from environment variables:

| Variable                                    | Default | Description                                            |
| ------------------------------------------- | ------- | ------------------------------------------------------ |
| `WORKFLOW_TASK_MAX_ATTEMPTS`                | `3`     | Maximum total attempts, including the initial attempt. |
| `WORKFLOW_TASK_RETRY_INITIAL_DELAY_SECONDS` | `1`     | Delay before the first retry.                          |
| `WORKFLOW_TASK_RETRY_BACKOFF_MULTIPLIER`    | `2`     | Exponential multiplier applied for each retry.         |
| `WORKFLOW_TASK_RETRY_MAX_DELAY_SECONDS`     | unset   | Optional upper bound for calculated retry delays.      |

Configure mock LLM behavior on the Worker process with environment variables:

| Variable                   | Default                     | Description                                                           |
| -------------------------- | --------------------------- | --------------------------------------------------------------------- |
| `MOCK_LLM_SEED`            | `0`                         | Seed used for deterministic response selection and failure decisions. |
| `MOCK_LLM_LATENCY_MS`      | `10`                        | Non-blocking simulated response delay in milliseconds.                |
| `MOCK_LLM_FORCE_FAIL`      | `false`                     | Set to `true` to fail every mock LLM task.                            |
| `MOCK_LLM_FAILURE_RATE`    | `0.0`                       | Simulated failure probability from `0.0` through `1.0`.               |
| `MOCK_LLM_FAILURE_MESSAGE` | `Mock LLM service failure.` | Error message for simulated failures.                                 |

## Mock external service configuration

Configure mock external-service behavior on the Worker process with environment variables. The
handler never makes an HTTP request; configured URLs and resolved workflow input are returned as
inert response data.

| Variable                                | Default                          | Description                                              |
| --------------------------------------- | -------------------------------- | -------------------------------------------------------- |
| `MOCK_EXTERNAL_SERVICE_SEED`            | `0`                              | Seed used for deterministic simulated failure decisions. |
| `MOCK_EXTERNAL_SERVICE_LATENCY_MS`      | `1500`                           | Non-blocking simulated response delay in milliseconds.   |
| `MOCK_EXTERNAL_SERVICE_FORCE_FAIL`      | `false`                          | Set to `true` to fail every mock external-service task.  |
| `MOCK_EXTERNAL_SERVICE_FAILURE_RATE`    | `0.0`                            | Simulated failure probability from `0.0` through `1.0`.  |
| `MOCK_EXTERNAL_SERVICE_FAILURE_MESSAGE` | `Mock external service failure.` | Error message for simulated failures.                    |

### Horizontal scaling example

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml up --build --scale api=3 --scale worker=4
```

### Verification

```bash
uv run pytest -q tests/docker
```

The Docker suite builds and exercises the actual Compose topology through the public API. It
covers the fan-out/fan-in workflow, scaled API and Worker replicas, Worker recovery, API restart,
and persisted state across application-container restarts. Docker must be running locally.

For a lightweight health and documentation check only:

```bash
bash tests/docker/verify_compose.sh
```

### Stop and clean up

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml down -v --remove-orphans
```

The Docker test suite uses an isolated named PostgreSQL volume and removes it during teardown.

## Architecture decision: Docker image targets

We use a single multi-stage Dockerfile with per-service build targets (`api`, `worker`, `migrate`) instead of multiple Dockerfiles. This keeps service images role-specific and slim while avoiding duplicated Dockerfile maintenance.

## Architecture decision: State authority and infrastructure initialization

PostgreSQL is the authoritative store for workflow and execution state. Redis (Streams) is used only as the asynchronous transport layer between API, Orchestrator, and Workers, and is not used as a source of truth.

Infrastructure initialization for both data systems follows an external initialization pattern:

- Database schema/state setup is handled by the DB migration/init flow.
- Redis stream and consumer-group provisioning is handled by a dedicated Redis init flow.

We codify these constraints in a dedicated Copilot workflow infrastructure instruction so future changes stay consistent across services. This reduces architectural drift by enforcing one shared rule set for state authority, initialization strategy, configuration, and messaging reliability.
