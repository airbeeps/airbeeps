"""Add message editing fields

Revision ID: add_message_editing
Revises: 2026_01_30_2500-add_audit_logs_and_user_roles
Create Date: 2026-01-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "add_message_editing"
down_revision = "4ud1t_l0g5_r0l35"  # add_audit_logs_and_user_roles migration
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add columns for message editing feature."""
    # Add columns one by one to avoid circular dependency issues
    # Check each column exists first to make migration idempotent

    if not _column_exists("messages", "edited_at"):
        with op.batch_alter_table("messages", schema=None) as batch_op:
            # Add edited_at column - timestamp when message was last edited
            batch_op.add_column(
                sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
            )

    if not _column_exists("messages", "original_content"):
        with op.batch_alter_table("messages", schema=None) as batch_op:
            # Add original_content column - stores the original content before first edit
            batch_op.add_column(
                sa.Column("original_content", sa.Text(), nullable=True),
            )

    if not _column_exists("messages", "is_regenerated"):
        with op.batch_alter_table("messages", schema=None) as batch_op:
            # Add is_regenerated column - flag for regenerated assistant responses
            batch_op.add_column(
                sa.Column(
                    "is_regenerated",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                ),
            )

    if not _column_exists("messages", "parent_message_id"):
        with op.batch_alter_table("messages", schema=None) as batch_op:
            # Add parent_message_id column - links regenerated messages to their parent
            batch_op.add_column(
                sa.Column(
                    "parent_message_id",
                    sa.UUID(),
                    nullable=True,
                ),
            )

            # Add foreign key constraint
            batch_op.create_foreign_key(
                "fk_messages_parent_message_id_messages",
                "messages",
                ["parent_message_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # Create index for faster lookups of edited messages if it doesn't exist
    # Note: SQLite doesn't support partial indexes, so we create a regular index
    conn = op.get_bind()
    inspector = inspect(conn)
    indexes = [idx["name"] for idx in inspector.get_indexes("messages")]
    if "ix_messages_edited_at" not in indexes:
        with op.batch_alter_table("messages", schema=None) as batch_op:
            batch_op.create_index(
                "ix_messages_edited_at",
                ["edited_at"],
                unique=False,
            )


def downgrade() -> None:
    """Remove message editing columns."""
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index("ix_messages_edited_at")
        batch_op.drop_constraint(
            "fk_messages_parent_message_id_messages", type_="foreignkey"
        )
        batch_op.drop_column("parent_message_id")
        batch_op.drop_column("is_regenerated")
        batch_op.drop_column("original_content")
        batch_op.drop_column("edited_at")
