"""Add updated_at to agent_traces

Revision ID: tr4c35t0r4g3y
Revises: tr4c35t0r4g3x
Create Date: 2026-01-30 10:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "tr4c35t0r4g3y"
down_revision: str | None = "tr4c35t0r4g3x"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add updated_at column to agent_traces
    # Check if column exists first (for SQLite compatibility)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("agent_traces")]

    if "updated_at" not in columns:
        op.add_column(
            "agent_traces",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    # Remove updated_at column
    op.drop_column("agent_traces", "updated_at")
