"""Persistence contract for idempotent worker processing by attempt."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.models.json import JsonValue
from app.domain.repositories.task_processing_repository import (
    TaskClaimOutcome,
    TaskProcessingResult,
)


class TaskAttemptProcessingRepository(Protocol):
    """Worker claim and result operations keyed by unique attempt IDs."""

    async def claim_attempt(
        self,
        attempt_id: UUID,
        task_id: str,
        execution_id: UUID,
        node_id: str,
        worker_id: str,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> TaskClaimOutcome:
        """Atomically claim one attempt or return its persisted state."""

    async def record_result(
        self,
        attempt_id: UUID,
        event_id: UUID,
        result_data: JsonValue,
        error_message: str | None,
        error_type: str | None,
    ) -> None:
        """Persist one attempt result before event publication."""

    async def get_result(self, attempt_id: UUID) -> TaskProcessingResult:
        """Retrieve a persisted attempt result for replay."""

    async def mark_completed(self, attempt_id: UUID, completed_at: datetime) -> None:
        """Mark an attempt complete after its event is published."""

    async def renew_claim(
        self,
        attempt_id: UUID,
        worker_id: str,
        claim_expires_at: datetime,
    ) -> bool:
        """Extend an active claim owned by one worker."""
