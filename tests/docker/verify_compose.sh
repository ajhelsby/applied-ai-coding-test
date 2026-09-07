#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker/docker-compose.yml"

docker compose -f "${COMPOSE_FILE}" up --build -d
trap 'docker compose -f "${COMPOSE_FILE}" down' EXIT

echo "Waiting for API health endpoint..."
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Verifying /health"
curl -fsS http://localhost:8000/health | cat

echo "Verifying /docs"
curl -fsS http://localhost:8000/docs >/dev/null

echo "Compose verification succeeded."
