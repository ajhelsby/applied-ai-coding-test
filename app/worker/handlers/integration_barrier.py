"""Integration-only worker handler for deterministic concurrency coordination."""

from __future__ import annotations

import os
from collections.abc import Mapping

from app.messaging.redis.barriers import participate_in_barrier
from app.messaging.redis.client import get_async_redis_client
from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler


class IntegrationBarrierNodeHandler(NodeHandler):
    """Hold a task until its integration-test barrier is released."""

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        if os.getenv("INTEGRATION_TEST") != "1":
            raise RuntimeError(
                "The integration barrier handler is only available in integration tests."
            )

        barrier = _barrier_config(task.handler_config)
        await participate_in_barrier(
            get_async_redis_client(),
            barrier["name"],
            barrier["participant"],
            timeout_seconds=_timeout_seconds(),
        )
        return {
            "barrier": barrier["name"],
            "participant": barrier["participant"],
            "status": "released",
        }


def _barrier_config(config: Mapping[str, object]) -> dict[str, str]:
    value = config.get("barrier")
    if not isinstance(value, Mapping):
        raise ValueError("Handler 'integration_barrier' requires a config.barrier object.")
    name = value.get("name")
    participant = value.get("participant")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Handler 'integration_barrier' requires a non-empty barrier.name.")
    if not isinstance(participant, str) or not participant.strip():
        raise ValueError("Handler 'integration_barrier' requires a non-empty barrier.participant.")
    return {"name": name, "participant": participant}


def _timeout_seconds() -> float:
    value = float(os.getenv("INTEGRATION_BARRIER_TIMEOUT_SECONDS", "30"))
    if value <= 0:
        raise ValueError("INTEGRATION_BARRIER_TIMEOUT_SECONDS must be greater than zero.")
    return value
