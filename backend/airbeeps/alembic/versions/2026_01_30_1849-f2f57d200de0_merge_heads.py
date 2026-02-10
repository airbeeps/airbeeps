"""merge_heads

Revision ID: f2f57d200de0
Revises: tr4c35t0r4g3y, m0d3l_4n4lyt1c5
Create Date: 2026-01-30 18:49:01.384798

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f2f57d200de0"
down_revision: str | Sequence[str] | None = ("tr4c35t0r4g3y", "m0d3l_4n4lyt1c5")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
