"""Merge the workflow migration branches.

Revision ID: b8c7d6e5f4a3
Revises: 7f3a2c1d9e80, 4e8b2c6d1f90
"""

from collections.abc import Sequence

revision: str = "b8c7d6e5f4a3"
down_revision: str | Sequence[str] | None = ("7f3a2c1d9e80", "4e8b2c6d1f90")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge migration branches without changing the schema."""


def downgrade() -> None:
    """Separate the migration branches again on downgrade."""
