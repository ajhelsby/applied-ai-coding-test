"""Add worker claim and result state to task attempts.

Revision ID: 4e8b2c6d1f90
Revises: 2d6f8a1c4b70
Create Date: 2026-09-16 10:58:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4e8b2c6d1f90"
down_revision: str | Sequence[str] | None = "2d6f8a1c4b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add durable worker claim and result columns to attempts."""
    op.add_column("task_attempts", sa.Column("claimed_by", sa.String(length=255), nullable=True))
    op.add_column(
        "task_attempts",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "task_attempts",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "task_attempts",
        sa.Column("result_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "task_attempts",
        sa.Column("completion_published_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove durable worker claim and result columns from attempts."""
    op.drop_column("task_attempts", "completion_published_at")
    op.drop_column("task_attempts", "result_data")
    op.drop_column("task_attempts", "claim_expires_at")
    op.drop_column("task_attempts", "claimed_at")
    op.drop_column("task_attempts", "claimed_by")
