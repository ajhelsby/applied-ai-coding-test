"""Mock external service node handler implementation."""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
from dataclasses import dataclass
from typing import ClassVar

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler


@dataclass(frozen=True, slots=True)
class MockExternalServiceSettings:
    """Application-level controls for mock external service behavior."""

    seed: int
    latency_ms: int
    force_fail: bool
    failure_rate: float
    failure_message: str


class MockExternalServiceNodeHandler(NodeHandler):
    """Return a deterministic response until external integration is implemented."""

    _DEFAULT_SEED: ClassVar[int] = 0
    _DEFAULT_LATENCY_MS: ClassVar[int] = 1_500
    _DEFAULT_FAILURE_RATE: ClassVar[float] = 0.0
    _DEFAULT_FAILURE_MESSAGE: ClassVar[str] = "Mock external service failure."

    def __init__(self, settings: MockExternalServiceSettings | None = None) -> None:
        self._settings = settings or self._settings_from_environment()

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        url = task.handler_config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Handler 'call_external_service' requires a non-empty config.url.")
        latency_ms = self._latency_ms(task.handler_config)
        await asyncio.sleep(latency_ms / 1000)
        generator = random.Random(self._random_seed(self._settings.seed, url))
        if self._settings.force_fail or generator.random() < self._settings.failure_rate:
            raise ValueError(self._settings.failure_message)
        return {
            "status": "mocked",
            "url": url,
            "input": dict(task.resolved_input),
        }

    def _latency_ms(self, config: dict[str, object]) -> int:
        configured_latency = config.get("latency_ms")
        if configured_latency is None:
            return self._settings.latency_ms
        if isinstance(configured_latency, bool) or not isinstance(configured_latency, int):
            raise ValueError(
                "Handler 'call_external_service' config.latency_ms must be an integer."
            )
        if configured_latency < 0:
            raise ValueError(
                "Handler 'call_external_service' config.latency_ms must be non-negative."
            )
        return configured_latency

    @classmethod
    def _settings_from_environment(cls) -> MockExternalServiceSettings:
        latency_ms = cls._integer_environment_value(
            "MOCK_EXTERNAL_SERVICE_LATENCY_MS",
            cls._DEFAULT_LATENCY_MS,
        )
        if latency_ms < 0:
            raise ValueError("MOCK_EXTERNAL_SERVICE_LATENCY_MS must be a non-negative integer.")

        failure_rate = cls._float_environment_value(
            "MOCK_EXTERNAL_SERVICE_FAILURE_RATE",
            cls._DEFAULT_FAILURE_RATE,
        )
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError("MOCK_EXTERNAL_SERVICE_FAILURE_RATE must be from 0 to 1.")

        failure_message = os.getenv(
            "MOCK_EXTERNAL_SERVICE_FAILURE_MESSAGE",
            cls._DEFAULT_FAILURE_MESSAGE,
        )
        if not failure_message:
            raise ValueError("MOCK_EXTERNAL_SERVICE_FAILURE_MESSAGE must be a non-empty string.")

        return MockExternalServiceSettings(
            seed=cls._integer_environment_value(
                "MOCK_EXTERNAL_SERVICE_SEED",
                cls._DEFAULT_SEED,
            ),
            latency_ms=latency_ms,
            force_fail=cls._boolean_environment_value(
                "MOCK_EXTERNAL_SERVICE_FORCE_FAIL",
                False,
            ),
            failure_rate=failure_rate,
            failure_message=failure_message,
        )

    @staticmethod
    def _integer_environment_value(name: str, default: int) -> int:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as error:
            raise ValueError(f"{name} must be an integer.") from error

    @staticmethod
    def _float_environment_value(name: str, default: float) -> float:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError as error:
            raise ValueError(f"{name} must be a number from 0 to 1.") from error

    @staticmethod
    def _boolean_environment_value(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        raise ValueError(f"{name} must be true or false.")

    @staticmethod
    def _random_seed(seed: int, url: str) -> int:
        url_hash = hashlib.sha256(url.encode("utf-8")).digest()
        return seed + int.from_bytes(url_hash, byteorder="big")
