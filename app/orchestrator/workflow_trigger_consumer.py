"""Redis consumer for workflow-execution trigger events."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.domain.repositories.unit_of_work import UnitOfWork
from app.messaging.redis.streams import (
    WORKFLOW_EVENTS_STREAM,
    ack,
    consume,
)
from app.messaging.stream_fields import json_object_field, required_field
from app.services.workflow_dispatch_service import WorkflowDispatchService
from app.services.workflow_readiness_service import WorkflowReadinessService

_ORCHESTRATOR_EVENTS_GROUP = "orchestrator"
_EXECUTION_TRIGGERED_EVENT_TYPE = "workflow.execution.triggered"


class WorkflowTriggerConsumer:
    """Promote and dispatch root nodes after an execution is triggered."""

    def __init__(
        self,
        consumer_name: str,
        unit_of_work_factory: Callable[[], UnitOfWork],
        readiness_service: WorkflowReadinessService | None = None,
        dispatch_service: WorkflowDispatchService | None = None,
    ) -> None:
        self._consumer_name = consumer_name
        self._unit_of_work_factory = unit_of_work_factory
        self._readiness_service = readiness_service or WorkflowReadinessService()
        self._dispatch_service = dispatch_service or WorkflowDispatchService()

    async def consume_once(self) -> int:
        """Process trigger events and acknowledge only after dispatch succeeds."""

        messages = await consume(
            group=_ORCHESTRATOR_EVENTS_GROUP,
            consumer=self._consumer_name,
            streams={WORKFLOW_EVENTS_STREAM: ">"},
            count=100,
            block_ms=1000,
        )
        processed = 0
        for stream, stream_messages in messages:
            for message_id, fields in stream_messages:
                event_type = required_field(fields, "event_type", "Workflow event")
                if event_type != _EXECUTION_TRIGGERED_EVENT_TYPE:
                    await ack(stream, _ORCHESTRATOR_EVENTS_GROUP, message_id)
                    processed += 1
                    continue
                execution_id = self._execution_id(fields)
                readiness = await self._readiness_service.evaluate(
                    execution_id,
                    self._unit_of_work_factory(),
                )
                await self._dispatch_service.dispatch_ready(
                    execution_id,
                    readiness.ready_node_ids,
                    self._unit_of_work_factory,
                )
                await ack(stream, _ORCHESTRATOR_EVENTS_GROUP, message_id)
                processed += 1
        return processed

    @staticmethod
    def _execution_id(fields: dict[str, str]) -> UUID:
        event_type = required_field(fields, "event_type", "Workflow event")
        if event_type != _EXECUTION_TRIGGERED_EVENT_TYPE:
            raise ValueError(f"Unsupported workflow event type '{event_type}'.")

        payload = json_object_field(fields, "payload", "Workflow event")
        raw_execution_id = payload.get("execution_id")
        if not isinstance(raw_execution_id, str):
            raise ValueError("Workflow event payload requires a string execution_id.")
        try:
            return UUID(raw_execution_id)
        except ValueError as error:
            raise ValueError("Workflow event payload execution_id must be a UUID.") from error
