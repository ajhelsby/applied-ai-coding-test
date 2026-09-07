"""baseline

Revision ID: 39323f5e8e55
Revises:
Create Date: 2026-09-07 12:17:44.508883

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "39323f5e8e55"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
