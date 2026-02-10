"""Remove deprecated KB fields (chunk_size, chunk_overlap, embedding_config)

Revision ID: f7g8h9i0j1k2
Revises: a1b2c3d4e5f6
Create Date: 2026-01-18 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7g8h9i0j1k2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove deprecated fields from knowledge_bases table.

    These fields are no longer used:
    - chunk_size: Now controlled by global RAG_HIERARCHICAL_CHUNK_SIZES config
    - chunk_overlap: Now controlled by global semantic chunking config
    - embedding_config: Replaced by direct embedding_model_id reference
    """
    # For SQLite, we need to recreate the table without these columns
    # For PostgreSQL/MySQL, we can use ALTER TABLE DROP COLUMN

    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.drop_column("chunk_size")
        batch_op.drop_column("chunk_overlap")
        batch_op.drop_column("embedding_config")


def downgrade() -> None:
    """Restore deprecated fields (for rollback only)."""
    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="512")
        )
        batch_op.add_column(
            sa.Column(
                "chunk_overlap", sa.Integer(), nullable=False, server_default="50"
            )
        )
        batch_op.add_column(
            sa.Column(
                "embedding_config", sa.JSON(), nullable=False, server_default="{}"
            )
        )
