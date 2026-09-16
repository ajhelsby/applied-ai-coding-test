"""Add durable worker task-processing state.

Revision ID: 9c4e2a7b1d60
Revises: 8a1f4c2d7e90
Create Date: 2026-09-16 10:21:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9c4e2a7b1d60"
down_revision: str | Sequence[str] | None = "8a1f4c2d7e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create durable worker task-processing state."""
    op.create_table(
        "task_processing",
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'claimed'"),
            nullable=False,
        ),
        sa.Column("claimed_by", sa.String(length=255), nullable=True),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("completion_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completion_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_task_processing_status", "task_processing", ["status"], unique=False)
    op.create_index(
        "ix_task_processing_execution_id_node_id",
        "task_processing",
        ["execution_id", "node_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop durable worker task-processing state."""
    op.drop_index(
        "ix_task_processing_execution_id_node_id",
        table_name="task_processing",
    )
    op.drop_index("ix_task_processing_status", table_name="task_processing")
    op.drop_table("task_processing")
