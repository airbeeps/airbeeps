"""add provider category

Revision ID: add_provider_category
Revises: 7a3c6f95150d
Create Date: 2026-01-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "add_provider_category"
down_revision: str | Sequence[str] | None = "7a3c6f95150d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite doesn't support ALTER COLUMN, so we need to use batch operations
    with op.batch_alter_table("model_providers", schema=None) as batch_op:
        # Add new columns (nullable initially for migration)
        batch_op.add_column(sa.Column("category", sa.String(50), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_openai_compatible",
                sa.Boolean(),
                nullable=True,
                server_default=sa.text("0"),
            )
        )

    # Migrate existing data based on interface_type and litellm_provider
    connection = op.get_bind()
    connection.execute(
        text("""
        UPDATE model_providers
        SET category = CASE
            WHEN interface_type = 'OPENAI' AND litellm_provider IS NOT NULL AND litellm_provider != '' THEN 'OPENAI_COMPATIBLE'
            WHEN interface_type = 'OPENAI' THEN 'PROVIDER_SPECIFIC'
            WHEN interface_type = 'HUGGINGFACE' THEN 'LOCAL'
            WHEN interface_type = 'ANTHROPIC' THEN 'PROVIDER_SPECIFIC'
            WHEN interface_type = 'GOOGLE' THEN 'PROVIDER_SPECIFIC'
            WHEN interface_type = 'XAI' THEN 'OPENAI_COMPATIBLE'
            ELSE 'PROVIDER_SPECIFIC'
        END,
        is_openai_compatible = CASE
            WHEN interface_type = 'OPENAI' AND litellm_provider IS NOT NULL AND litellm_provider != '' THEN 1
            WHEN interface_type = 'XAI' THEN 1
            ELSE 0
        END
    """)
    )

    # Set default litellm_provider for rows that don't have one
    connection.execute(
        text("""
        UPDATE model_providers
        SET litellm_provider = CASE
            WHEN litellm_provider IS NULL OR litellm_provider = '' THEN
                CASE interface_type
                    WHEN 'OPENAI' THEN 'openai'
                    WHEN 'ANTHROPIC' THEN 'anthropic'
                    WHEN 'GOOGLE' THEN 'gemini'
                    WHEN 'XAI' THEN 'xai'
                    WHEN 'HUGGINGFACE' THEN 'huggingface'
                    ELSE 'openai'
                END
            ELSE litellm_provider
        END
    """)
    )

    # Now make columns non-nullable using batch operations
    with op.batch_alter_table("model_providers", schema=None) as batch_op:
        batch_op.alter_column("category", nullable=False)
        batch_op.alter_column(
            "is_openai_compatible", nullable=False, server_default=None
        )
        batch_op.alter_column("litellm_provider", nullable=False)
        batch_op.alter_column("interface_type", nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Restore interface_type as non-nullable
    connection = op.get_bind()
    connection.execute(
        text("""
        UPDATE model_providers
        SET interface_type = CASE
            WHEN category = 'OPENAI_COMPATIBLE' THEN 'OPENAI'
            WHEN category = 'PROVIDER_SPECIFIC' THEN 'OPENAI'
            WHEN category = 'LOCAL' THEN 'HUGGINGFACE'
            WHEN category = 'CUSTOM' THEN 'CUSTOM'
            ELSE 'CUSTOM'
        END
        WHERE interface_type IS NULL
    """)
    )

    with op.batch_alter_table("model_providers", schema=None) as batch_op:
        batch_op.alter_column("interface_type", nullable=False)
        batch_op.alter_column("litellm_provider", nullable=True)
        batch_op.drop_column("is_openai_compatible")
        batch_op.drop_column("category")
