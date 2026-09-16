"""Application service for deriving terminal workflow execution state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from app.domain.errors.transitions import WorkflowExecutionNotFoundError
from app.domain.models.execution import WorkflowExecution
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.state.states import NodeExecutionStatus, WorkflowExecutionStatus
from app.messaging.redis.streams import WORKFLOW_EVENTS_STREAM

_WORKFLOW_EVENT_NAMESPACE = UUID("f4e6d6a6-5f24-4e5a-b8fb-cc2f7c6a0c0e")


@dataclass(frozen=True, slots=True)
class WorkflowFinalizationDecision:
    """The workflow state after evaluating terminal conditions."""

    execution_id: UUID
    status: WorkflowExecutionStatus


class WorkflowFinalizationService:
    """Transition running workflows to a terminal state when their nodes require it."""

    async def evaluate(
        self,
        execution_id: UUID,
        unit_of_work: UnitOfWork,
    ) -> WorkflowFinalizationDecision:
        """Fail on any failed node, or complete when every defined node completed."""

        async with unit_of_work.transaction() as transaction:
            execution = await transaction.workflow_executions.get_execution_by_id(execution_id)
            if execution is None:
                raise WorkflowExecutionNotFoundError(str(execution_id))

            decision = await self.evaluate_in_transaction(
                execution_id,
                transaction,
                execution,
            )
        return decision

    async def evaluate_in_transaction(
        self,
        execution_id: UUID,
        transaction: UnitOfWork,
        execution: WorkflowExecution | None = None,
        correlation_id: UUID | None = None,
    ) -> WorkflowFinalizationDecision:
        """Evaluate terminal workflow state inside an existing transaction."""

        persisted_execution = (
            execution or await transaction.workflow_executions.get_execution_by_id(execution_id)
        )
        if persisted_execution is None:
            raise WorkflowExecutionNotFoundError(str(execution_id))

        node_executions = await transaction.node_executions.get_node_executions_for_execution(
            execution_id
        )
        if any(item.status is NodeExecutionStatus.FAILED for item in node_executions):
            updated = await transaction.workflow_executions.update_status_if_current(
                execution_id=execution_id,
                expected_current_status=WorkflowExecutionStatus.RUNNING,
                new_status=WorkflowExecutionStatus.FAILED,
                completed_at=datetime.now(UTC),
            )
            if updated:
                await transaction.outbox_events.add_message(
                    message_id=_workflow_event_id(correlation_id, execution_id, "failed"),
                    message_type="workflow.execution.failed",
                    target_stream=WORKFLOW_EVENTS_STREAM,
                    aggregate_id=execution_id,
                    payload={"execution_id": str(execution_id), "status": "failed"},
                )
            return WorkflowFinalizationDecision(
                execution_id=execution_id,
                status=WorkflowExecutionStatus.FAILED,
            )

        workflow = await transaction.workflows.get_workflow_by_id(persisted_execution.workflow_id)
        if workflow is None:
            raise LookupError(f"Workflow '{persisted_execution.workflow_id}' was not found.")

        node_statuses_by_id = {item.node_id: item.status for item in node_executions}
        if all(
            node_statuses_by_id.get(node.id) is NodeExecutionStatus.COMPLETED
            for node in workflow.dag.nodes
        ):
            updated = await transaction.workflow_executions.update_status_if_current(
                execution_id=execution_id,
                expected_current_status=WorkflowExecutionStatus.RUNNING,
                new_status=WorkflowExecutionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            if updated:
                await transaction.outbox_events.add_message(
                    message_id=_workflow_event_id(correlation_id, execution_id, "completed"),
                    message_type="workflow.execution.completed",
                    target_stream=WORKFLOW_EVENTS_STREAM,
                    aggregate_id=execution_id,
                    payload={"execution_id": str(execution_id), "status": "completed"},
                )
            return WorkflowFinalizationDecision(
                execution_id=execution_id,
                status=WorkflowExecutionStatus.COMPLETED,
            )

        return WorkflowFinalizationDecision(
            execution_id=execution_id,
            status=persisted_execution.status,
        )


def _workflow_event_id(correlation_id: UUID | None, execution_id: UUID, status: str) -> UUID:
    """Create a stable lifecycle event ID for a state transition."""
    if correlation_id is not None:
        return uuid5(correlation_id, f"workflow:{execution_id}:{status}")
    return uuid4()
