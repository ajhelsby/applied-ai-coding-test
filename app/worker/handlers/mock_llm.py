"""Mock LLM service node handler implementation."""

from __future__ import annotations

import asyncio
import hashlib
import random
from collections.abc import Mapping
from typing import ClassVar, NotRequired, TypedDict

from app.messaging.task_messages import NodeTaskMessage
from app.worker.handlers.base import NodeHandler


class MockLlmServiceConfig(TypedDict):
    """Optional controls for the mock LLM service handler."""

    seed: NotRequired[int]
    latency_ms: NotRequired[int]
    force_fail: NotRequired[bool]
    failure_rate: NotRequired[float]
    failure_message: NotRequired[str]


class ParsedMockLlmServiceConfig(TypedDict):
    """Validated mock LLM service controls with all defaults applied."""

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

    async def execute(self, task: NodeTaskMessage) -> dict[str, object]:
        """Return a deterministic text response for an inert resolved prompt."""

        prompt = self._prompt(task.resolved_input)
        config = self._config(task.handler_config)
        await asyncio.sleep(config["latency_ms"] / 1000)

        generator = random.Random(self._random_seed(config["seed"], prompt))
        if config["force_fail"] or generator.random() < config["failure_rate"]:
            raise ValueError(config["failure_message"])

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
    def _config(cls, handler_config: Mapping[str, object]) -> ParsedMockLlmServiceConfig:
        seed = handler_config.get("seed", cls._DEFAULT_SEED)
        latency_ms = handler_config.get("latency_ms", cls._DEFAULT_LATENCY_MS)
        force_fail = handler_config.get("force_fail", False)
        failure_rate = handler_config.get("failure_rate", cls._DEFAULT_FAILURE_RATE)
        failure_message = handler_config.get("failure_message", cls._DEFAULT_FAILURE_MESSAGE)

        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("Handler 'llm_service' config.seed must be an integer.")
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or latency_ms < 0:
            raise ValueError(
                "Handler 'llm_service' config.latency_ms must be a non-negative integer."
            )
        if not isinstance(force_fail, bool):
            raise ValueError("Handler 'llm_service' config.force_fail must be a boolean.")
        if isinstance(failure_rate, bool) or not isinstance(failure_rate, (int, float)):
            raise ValueError(
                "Handler 'llm_service' config.failure_rate must be a number from 0 to 1."
            )
        normalized_failure_rate = float(failure_rate)
        if not 0.0 <= normalized_failure_rate <= 1.0:
            raise ValueError("Handler 'llm_service' config.failure_rate must be from 0 to 1.")
        if not isinstance(failure_message, str) or not failure_message:
            raise ValueError(
                "Handler 'llm_service' config.failure_message must be a non-empty string."
            )

        return {
            "seed": seed,
            "latency_ms": latency_ms,
            "force_fail": force_fail,
            "failure_rate": normalized_failure_rate,
            "failure_message": failure_message,
        }

    @staticmethod
    def _random_seed(seed: int, prompt: str) -> int:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).digest()
        return seed + int.from_bytes(prompt_hash, byteorder="big")
