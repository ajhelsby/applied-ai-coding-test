import asyncio
import logging
import os
import signal

from redis.exceptions import RedisError

from app.db.session import close_database_connections
from app.messaging.redis.client import close_async_redis_client
from app.orchestrator.outbox import publish_outbox_events

logger = logging.getLogger(__name__)
running = True


def _handle_signal(signum: int, _frame: object) -> None:
    del signum
    global running
    running = False


async def run() -> None:
    """Continuously publish durable workflow trigger events."""

    poll_interval_seconds = float(os.getenv("OUTBOX_POLL_INTERVAL_SECONDS", "1"))

    while running:
        try:
            published = await publish_outbox_events()
            if published:
                logger.info("Published workflow outbox events", extra={"event_count": published})
        except RedisError:
            logger.exception("Unable to publish workflow outbox events; will retry")
        await asyncio.sleep(poll_interval_seconds)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log_level = os.getenv("LOG_LEVEL", "INFO")
    print(f"orchestrator started (LOG_LEVEL={log_level})", flush=True)
    try:
        asyncio.run(run())
    finally:
        asyncio.run(close_async_redis_client())
        asyncio.run(close_database_connections())
        print("orchestrator stopped", flush=True)


if __name__ == "__main__":
    main()
