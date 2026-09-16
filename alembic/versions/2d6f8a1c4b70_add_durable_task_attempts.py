"""Add durable logical-task retry state and attempt history.

Revision ID: 2d6f8a1c4b70
Revises: 9c4e2a7b1d60
Create Date: 2026-09-16 10:53:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2d6f8a1c4b70"
down_revision: str | Sequence[str] | None = "9c4e2a7b1d60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create durable logical-task, attempt, and retry-dispatch state."""
    op.create_table(
        "logical_tasks",
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("handler", sa.String(length=255), nullable=False),
        sa.Column("handler_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolved_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("final_error_message", sa.Text(), nullable=True),
        sa.Column("final_error_type", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["workflow_executions.execution_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(
        "ix_logical_tasks_execution_id_node_id",
        "logical_tasks",
        ["execution_id", "node_id"],
        unique=True,
    )

    op.create_table(
        "task_attempts",
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "failure_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "completion_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["logical_tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_task_attempts_task_number"),
        sa.UniqueConstraint("failure_event_id", name="uq_task_attempts_failure_event_id"),
    )
    op.create_index(
        "ix_task_attempts_task_id_status",
        "task_attempts",
        ["task_id", "status"],
        unique=False,
    )

    op.create_table(
        "task_retry_dispatches",
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["task_attempts.attempt_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_task_retry_dispatches_due",
        "task_retry_dispatches",
        ["status", "available_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop durable logical-task, attempt, and retry-dispatch state."""
    op.drop_index("ix_task_retry_dispatches_due", table_name="task_retry_dispatches")
    op.drop_table("task_retry_dispatches")
    op.drop_index("ix_task_attempts_task_id_status", table_name="task_attempts")
    op.drop_table("task_attempts")
    op.drop_index("ix_logical_tasks_execution_id_node_id", table_name="logical_tasks")
    op.drop_table("logical_tasks")
