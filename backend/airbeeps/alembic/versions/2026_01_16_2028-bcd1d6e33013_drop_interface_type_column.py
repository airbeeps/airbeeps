"""drop_interface_type_column

Revision ID: bcd1d6e33013
Revises: add_provider_category
Create Date: 2026-01-16 20:28:07.600516

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bcd1d6e33013"
down_revision: str | Sequence[str] | None = "add_provider_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop interface_type column from model_providers table
    op.drop_column("model_providers", "interface_type")


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add interface_type column for downgrade
    op.add_column(
        "model_providers", sa.Column("interface_type", sa.String(50), nullable=True)
    )
