# applied-ai-coding-test

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
