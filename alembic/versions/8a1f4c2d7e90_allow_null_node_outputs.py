"""Allow successful nodes to persist JSON null output."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8a1f4c2d7e90"
down_revision: str | Sequence[str] | None = "571dc8014b2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow node output data to be JSON null."""

    op.alter_column(
        "node_executions",
        "output_data",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )


def downgrade() -> None:
    """Restore the required node output data constraint."""

    op.alter_column(
        "node_executions",
        "output_data",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
