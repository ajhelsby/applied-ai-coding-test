"""Task-processing persistence contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.domain.models.json import JsonValue


class TaskClaimOutcome(StrEnum):
    """Outcome of attempting to claim a task for execution."""

    CLAIMED = "claimed"
    ALREADY_COMPLETED = "already_completed"
    CURRENTLY_CLAIMED = "currently_claimed"
    RESULT_RECORDED = "result_recorded"


@dataclass(frozen=True, slots=True)
class TaskProcessingResult:
    """Persisted worker result available for completion-event replay."""

    event_id: UUID
    result_data: JsonValue
    error_message: str | None
    error_type: str | None


class TaskProcessingRepository(Protocol):
    """Persistence operations for idempotent worker task processing."""

    async def claim_task(
        self,
        task_id: str,
        execution_id: UUID,
        node_id: str,
        worker_id: str,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> TaskClaimOutcome:
        """Atomically claim a task or return its existing processing state."""

    async def record_result(
        self,
        task_id: str,
        event_id: UUID,
        result_data: JsonValue,
        error_message: str | None,
        error_type: str | None,
    ) -> None:
        """Persist a handler result before publishing its completion event."""

    async def get_result(self, task_id: str) -> TaskProcessingResult:
        """Retrieve a persisted result for completion-event replay."""

    async def mark_completed(self, task_id: str, completed_at: datetime) -> None:
        """Mark a result as completed after its completion event is published."""

    async def renew_claim(
        self,
        task_id: str,
        worker_id: str,
        claim_expires_at: datetime,
    ) -> bool:
        """Extend an active claim owned by a worker."""
