"""Add LlamaIndex RAG fields to KnowledgeBase

Revision ID: a1b2c3d4e5f6
Revises: bcd1d6e33013
Create Date: 2026-01-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "bcd1d6e33013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add vector_store_type, vector_store_config, and retrieval_config to knowledge_bases."""
    # Add vector_store_type column with default 'qdrant'
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "vector_store_type",
            sa.String(20),
            nullable=False,
            server_default="qdrant",
        ),
    )

    # Add vector_store_config JSON column
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "vector_store_config",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )

    # Add retrieval_config JSON column
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "retrieval_config",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )

    # Update default chunk_size from 500 to 512
    # (SQLite doesn't support ALTER COLUMN, so we keep the existing default)


def downgrade() -> None:
    """Remove LlamaIndex RAG fields."""
    op.drop_column("knowledge_bases", "retrieval_config")
    op.drop_column("knowledge_bases", "vector_store_config")
    op.drop_column("knowledge_bases", "vector_store_type")
