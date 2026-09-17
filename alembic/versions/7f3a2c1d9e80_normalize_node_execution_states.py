"""Normalize node execution states to the four supported lifecycle states.

Revision ID: 7f3a2c1d9e80
Revises: 6c2e1f4a9b70
Create Date: 2026-09-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7f3a2c1d9e80"
down_revision: str | Sequence[str] | None = "6c2e1f4a9b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Map legacy transitional states to supported lifecycle states."""

    op.execute(sa.text("UPDATE node_executions SET status = 'pending' WHERE status = 'ready'"))
    op.execute(sa.text("UPDATE node_executions SET status = 'failed' WHERE status = 'skipped'"))
    op.create_check_constraint(
        "ck_node_executions_status",
        "node_executions",
        "status IN ('pending', 'running', 'completed', 'failed')",
    )


def downgrade() -> None:
    """Leave normalized lifecycle states unchanged on downgrade."""

    op.drop_constraint("ck_node_executions_status", "node_executions", type_="check")
