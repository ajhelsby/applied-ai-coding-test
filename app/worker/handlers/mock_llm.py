"""Mock LLM service node handler implementation."""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler


@dataclass(frozen=True, slots=True)
class MockLlmServiceSettings:
    """Application-level controls for mock LLM service behavior."""

    seed: int
    latency_ms: int
    force_fail: bool
    failure_rate: float
    failure_message: str


class MockLlmServiceNodeHandler(NodeHandler):
    """Generate deterministic mock text without invoking an LLM or external service."""

    _DEFAULT_SEED: ClassVar[int] = 0
    _DEFAULT_LATENCY_MS: ClassVar[int] = 10
    _DEFAULT_FAILURE_RATE: ClassVar[float] = 0.0
    _DEFAULT_FAILURE_MESSAGE: ClassVar[str] = "Mock LLM service failure."
    _MAX_PROMPT_SNIPPET_LENGTH: ClassVar[int] = 160
    _RESPONSE_TEMPLATES: ClassVar[tuple[str, ...]] = (
        "Mock analysis: {prompt}",
        "Mock generated response based on: {prompt}",
        "Mock completion: {prompt}",
    )

    def __init__(self, settings: MockLlmServiceSettings | None = None) -> None:
        self._settings = settings or self._settings_from_environment()

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        """Return a deterministic text response for an inert resolved prompt."""

        prompt = self._prompt(task.resolved_input)
        await asyncio.sleep(self._settings.latency_ms / 1000)

        generator = random.Random(self._random_seed(self._settings.seed, prompt))
        if self._settings.force_fail or generator.random() < self._settings.failure_rate:
            raise ValueError(self._settings.failure_message)

        template = generator.choice(self._RESPONSE_TEMPLATES)
        return {
            "response": template.format(prompt=prompt[: self._MAX_PROMPT_SNIPPET_LENGTH]),
        }

    @staticmethod
    def _prompt(resolved_input: Mapping[str, object]) -> str:
        prompt = resolved_input.get("prompt")
        if not isinstance(prompt, str):
            raise ValueError("Handler 'llm_service' requires a string resolved_input.prompt.")
        return prompt

    @classmethod
    def _settings_from_environment(cls) -> MockLlmServiceSettings:
        latency_ms = cls._integer_environment_value("MOCK_LLM_LATENCY_MS", cls._DEFAULT_LATENCY_MS)
        if latency_ms < 0:
            raise ValueError("MOCK_LLM_LATENCY_MS must be a non-negative integer.")

        failure_rate = cls._float_environment_value(
            "MOCK_LLM_FAILURE_RATE", cls._DEFAULT_FAILURE_RATE
        )
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError("MOCK_LLM_FAILURE_RATE must be from 0 to 1.")

        failure_message = os.getenv("MOCK_LLM_FAILURE_MESSAGE", cls._DEFAULT_FAILURE_MESSAGE)
        if not failure_message:
            raise ValueError("MOCK_LLM_FAILURE_MESSAGE must be a non-empty string.")

        return MockLlmServiceSettings(
            seed=cls._integer_environment_value("MOCK_LLM_SEED", cls._DEFAULT_SEED),
            latency_ms=latency_ms,
            force_fail=cls._boolean_environment_value("MOCK_LLM_FORCE_FAIL", False),
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
    def _random_seed(seed: int, prompt: str) -> int:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).digest()
        return seed + int.from_bytes(prompt_hash, byteorder="big")
