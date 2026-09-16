"""Generalize transactional outbox messages.

Revision ID: 6c2e1f4a9b70
Revises: 571dc8014b2c
Create Date: 2026-09-16 12:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6c2e1f4a9b70"
down_revision: str | Sequence[str] | None = "571dc8014b2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename event-specific columns and add the target stream."""
    op.drop_constraint(
        "outbox_events_aggregate_id_fkey",
        "outbox_events",
        type_="foreignkey",
    )
    op.alter_column("outbox_events", "event_id", new_column_name="message_id")
    op.alter_column("outbox_events", "event_type", new_column_name="message_type")
    op.alter_column(
        "outbox_events",
        "aggregate_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.add_column(
        "outbox_events",
        sa.Column("target_stream", sa.String(length=128), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE outbox_events SET target_stream = 'workflow.events' WHERE target_stream IS NULL"
        )
    )
    op.alter_column(
        "outbox_events",
        "target_stream",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.create_index(
        "ix_outbox_events_target_stream_status",
        "outbox_events",
        ["target_stream", "status"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_published_at",
        "outbox_events",
        ["published_at"],
        unique=False,
    )


def downgrade() -> None:
    """Restore the event-specific outbox schema."""
    op.drop_index("ix_outbox_events_published_at", table_name="outbox_events")
    op.drop_index("ix_outbox_events_target_stream_status", table_name="outbox_events")
    op.drop_column("outbox_events", "target_stream")
    op.alter_column(
        "outbox_events",
        "aggregate_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.alter_column("outbox_events", "message_type", new_column_name="event_type")
    op.alter_column("outbox_events", "message_id", new_column_name="event_id")
    op.create_foreign_key(
        "outbox_events_aggregate_id_fkey",
        "outbox_events",
        "workflow_executions",
        ["aggregate_id"],
        ["execution_id"],
        ondelete="CASCADE",
    )
