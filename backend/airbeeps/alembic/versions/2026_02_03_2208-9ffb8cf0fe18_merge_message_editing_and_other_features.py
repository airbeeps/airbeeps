"""merge message editing and other features

Revision ID: 9ffb8cf0fe18
Revises: f2f57d200de0, add_message_editing
Create Date: 2026-02-03 22:08:54.874523

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "9ffb8cf0fe18"
down_revision: str | Sequence[str] | None = ("f2f57d200de0", "add_message_editing")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
