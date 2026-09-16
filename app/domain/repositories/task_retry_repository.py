"""Persistence contract for logical task retry decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class RetryDecisionOutcome(StrEnum):
    """Outcome of applying one worker completion event to retry state."""

    RETRY_SCHEDULED = "retry_scheduled"
    EXHAUSTED = "exhausted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Durable result of processing a failed attempt."""

    outcome: RetryDecisionOutcome
    next_attempt_id: UUID | None = None
    next_attempt_number: int | None = None


@dataclass(frozen=True, slots=True)
class DueRetryTask:
    """Persisted retry payload ready for publication."""

    task_id: str
    attempt_id: UUID
    attempt_number: int
    execution_id: UUID
    node_id: str
    handler: str
    handler_config: dict[str, object]
    resolved_input: dict[str, object]


class TaskRetryRepository(Protocol):
    """Transactional persistence operations for retry decisions."""

    async def record_success(
        self,
        task_id: str,
        attempt_id: UUID,
        completion_event_id: UUID,
        completed_at: datetime,
    ) -> bool:
        """Record a successful attempt, returning false for a duplicate event."""

    async def record_failure(
        self,
        task_id: str,
        attempt_id: UUID,
        failure_event_id: UUID,
        error_message: str,
        error_type: str,
        failed_at: datetime,
        max_attempts: int,
        retry_at: datetime,
    ) -> RetryDecision:
        """Atomically deduplicate, record, and schedule a failed attempt."""

    async def register_initial_task(
        self,
        task_id: str,
        execution_id: UUID,
        node_id: str,
        handler: str,
        handler_config: dict[str, object],
        resolved_input: dict[str, object],
        attempt_id: UUID,
        started_at: datetime,
    ) -> UUID:
        """Persist the logical task and its first attempt idempotently."""

    async def get_due_retries(self, available_at: datetime) -> list[DueRetryTask]:
        """Load retries whose durable delay has elapsed."""

    async def mark_retry_published(self, attempt_id: UUID, published_at: datetime) -> bool:
        """Mark one retry as published, returning false if already published."""
