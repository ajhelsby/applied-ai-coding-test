# applied-ai-coding-test

## Requirements

- Python 3.12
- Docker and Docker Compose
- Node.js (required for running all `pre-commit` hooks, including JS-based hooks)

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

### Horizontal scaling example

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml up --build --scale api=3 --scale worker=4
```

### Verification

```bash
bash tests/docker/verify_compose.sh
```

### Stop and clean up

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml down
```

PostgreSQL data is persisted in `docker/db/postgres_data`.

## Architecture decision: Docker image targets

We use a single multi-stage Dockerfile with per-service build targets (`api`, `worker`, `migrate`) instead of multiple Dockerfiles. This keeps service images role-specific and slim while avoiding duplicated Dockerfile maintenance.

## Architecture decision: State authority and infrastructure initialization

PostgreSQL is the authoritative store for workflow and execution state. Redis (Streams) is used only as the asynchronous transport layer between API, Orchestrator, and Workers, and is not used as a source of truth.

Infrastructure initialization for both data systems follows an external initialization pattern:

- Database schema/state setup is handled by the DB migration/init flow.
- Redis stream and consumer-group provisioning is handled by a dedicated Redis init flow.

We codify these constraints in a dedicated Copilot workflow infrastructure instruction so future changes stay consistent across services. This reduces architectural drift by enforcing one shared rule set for state authority, initialization strategy, configuration, and messaging reliability.
