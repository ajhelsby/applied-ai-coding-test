#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker/docker-compose.yml"
ENV_FILE="docker/.env"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up --build -d
trap 'docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" down' EXIT

echo "Waiting for API health endpoint..."
for _ in $(seq 1 60); do
  api_port="$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" port api 8000 \
    | sed -n '1s/.*://p')"
  if [ -n "${api_port}" ] && curl -fsS "http://localhost:${api_port}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

api_port="$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" port api 8000 \
  | sed -n '1s/.*://p')"

echo "Verifying /health"
curl -fsS "http://localhost:${api_port}/health" | cat

echo "Verifying /docs"
curl -fsS "http://localhost:${api_port}/docs" >/dev/null

echo "Compose verification succeeded."
