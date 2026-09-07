import os
from typing import Final, cast

import redis
from redis import Redis
from redis import asyncio as aioredis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

_REDIS_URL_ENV: Final[str] = "REDIS_URL"
_redis_client: Redis[str] | None = None
_async_redis_client: aioredis.Redis[str] | None = None


def _get_redis_url() -> str:
    redis_url = os.getenv(_REDIS_URL_ENV)
    if not redis_url:
        raise RuntimeError(f"{_REDIS_URL_ENV} environment variable is required")
    return redis_url


def get_redis_client() -> Redis[str]:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            _get_redis_url(),
            decode_responses=True,
            retry=Retry(ExponentialBackoff(base=1, cap=10), retries=5),
            retry_on_error=[redis.ConnectionError, redis.TimeoutError],
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
    return _redis_client


def ping_redis() -> bool:
    return bool(get_redis_client().ping())


def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None


def get_async_redis_client() -> aioredis.Redis[str]:
    global _async_redis_client
    if _async_redis_client is None:
        _async_redis_client = cast(
            aioredis.Redis[str],
            aioredis.from_url(
                _get_redis_url(),
                decode_responses=True,
                retry=Retry(ExponentialBackoff(base=1, cap=10), retries=5),
                retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
            ),
        )
    return _async_redis_client


async def ping_async_redis() -> bool:
    return bool(await get_async_redis_client().ping())


async def close_async_redis_client() -> None:
    global _async_redis_client
    if _async_redis_client is not None:
        await _async_redis_client.close()
        _async_redis_client = None
