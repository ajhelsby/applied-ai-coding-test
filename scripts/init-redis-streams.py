import os

import redis  # type: ignore[import-untyped]

TASKS_STREAM = "workflow.tasks"
EVENTS_STREAM = "workflow.events"
WORKER_GROUP = "workers"
ORCHESTRATOR_GROUP = "orchestrator"


def ensure_group(client: redis.Redis, stream: str, group: str) -> None:
    try:
        client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
        print(f"created consumer group '{group}' for stream '{stream}'", flush=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            print(f"consumer group '{group}' already exists for stream '{stream}'", flush=True)
            return
        raise


def main() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable is required")

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    try:
        client.ping()
        ensure_group(client, TASKS_STREAM, WORKER_GROUP)
        ensure_group(client, EVENTS_STREAM, ORCHESTRATOR_GROUP)
    finally:
        client.close()


if __name__ == "__main__":
    main()
