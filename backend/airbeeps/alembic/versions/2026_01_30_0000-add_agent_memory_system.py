"""Add agent memory system tables

Revision ID: m3m0ry5y5t3m
Revises: k3l4m5n6o7p8
Create Date: 2026-01-30 00:00:00.000000

"""

from collections.abc import Sequence

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m3m0ry5y5t3m"
down_revision: str | None = "k3l4m5n6o7p8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create memory_retention_policies table
    op.create_table(
        "memory_retention_policies",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "ttl_days",
            sa.Integer(),
            nullable=False,
            server_default="90",
            comment="Days before memory expires (0 = never)",
        ),
        sa.Column(
            "max_memories_per_user",
            sa.Integer(),
            nullable=False,
            server_default="1000",
            comment="Maximum memories per user",
        ),
        sa.Column(
            "auto_prune_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.3",
            comment="Importance score below which memories are pruned",
        ),
        sa.Column(
            "applies_to_types",
            sa.JSON(),
            nullable=False,
            server_default='["CONVERSATION", "EPISODIC", "SEMANTIC", "PREFERENCE"]',
            comment="Memory types this policy applies to",
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this is the default retention policy",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create agent_memories table
    op.create_table(
        "agent_memories",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "assistant_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "memory_type",
            sa.Enum(
                "CONVERSATION",
                "EPISODIC",
                "SEMANTIC",
                "PREFERENCE",
                name="memorytypeenum",
            ),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="Encrypted memory content",
        ),
        sa.Column(
            "embedding",
            sa.JSON(),
            nullable=True,
            comment="Embedding vector for semantic search",
        ),
        sa.Column(
            "embedding_dim",
            sa.Integer(),
            nullable=True,
            comment="Dimension of embedding vector",
        ),
        sa.Column(
            "importance_score",
            sa.Float(),
            nullable=False,
            server_default="0.5",
            comment="Importance score for pruning decisions",
        ),
        sa.Column(
            "access_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of times this memory was retrieved",
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this memory was last retrieved",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Additional metadata about the memory",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this memory expires (null = never)",
        ),
        sa.Column(
            "is_encrypted",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether content is encrypted",
        ),
        sa.Column(
            "retention_policy_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column(
            "source_conversation_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
            comment="Conversation this memory was derived from",
        ),
        sa.Column(
            "source_message_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
            comment="Message this memory was derived from",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assistant_id"], ["assistants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["retention_policy_id"],
            ["memory_retention_policies.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for agent_memories
    op.create_index(
        "ix_agent_memories_assistant_id", "agent_memories", ["assistant_id"]
    )
    op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"])
    op.create_index("ix_agent_memories_memory_type", "agent_memories", ["memory_type"])
    op.create_index("ix_agent_memories_expires_at", "agent_memories", ["expires_at"])
    op.create_index(
        "ix_agent_memories_user_assistant",
        "agent_memories",
        ["user_id", "assistant_id"],
    )
    op.create_index(
        "ix_agent_memories_user_type",
        "agent_memories",
        ["user_id", "memory_type"],
    )

    # Create user_memory_consents table
    op.create_table(
        "user_memory_consents",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "has_consented",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether user has consented to memory storage",
        ),
        sa.Column(
            "consent_date",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When consent was last modified",
        ),
        sa.Column(
            "allowed_memory_types",
            sa.JSON(),
            nullable=False,
            server_default='["CONVERSATION", "EPISODIC", "SEMANTIC", "PREFERENCE"]',
            comment="Which memory types the user consents to",
        ),
        sa.Column(
            "preferred_ttl_days",
            sa.Integer(),
            nullable=True,
            comment="User's preferred retention period in days",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_memory_consents_user_id", "user_memory_consents", ["user_id"]
    )

    # Create memory_consent_logs table for GDPR audit
    op.create_table(
        "memory_consent_logs",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Enum("GRANT", "REVOKE", "EXPORT", "DELETE", name="consentactionenum"),
            nullable=False,
        ),
        sa.Column(
            "action_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ip_address",
            sa.String(50),
            nullable=True,
            comment="IP address from which action was taken",
        ),
        sa.Column(
            "user_agent",
            sa.String(500),
            nullable=True,
            comment="User agent of the request",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Additional action details",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_consent_logs_user_id", "memory_consent_logs", ["user_id"]
    )

    # Add assistant field for memory feature toggle (only if doesn't exist)
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("assistants")]

    if "enable_memory" not in columns:
        op.add_column(
            "assistants",
            sa.Column(
                "enable_memory",
                sa.Boolean(),
                nullable=False,
                server_default="false",
                comment="Whether to enable long-term memory for this assistant",
            ),
        )

    # Insert default retention policy (SQLite-compatible)
    import uuid
    from datetime import datetime

    from sqlalchemy import text

    default_policy_id = str(uuid.uuid4())
    op.execute(
        text("""
        INSERT OR IGNORE INTO memory_retention_policies (id, name, description, ttl_days, max_memories_per_user,
            auto_prune_threshold, applies_to_types, is_default, is_active, created_at)
        VALUES (
            :id,
            'default',
            'Default retention policy for all memory types',
            90,
            1000,
            0.3,
            '["CONVERSATION", "EPISODIC", "SEMANTIC", "PREFERENCE"]',
            1,
            1,
            :created_at
        )
        """).bindparams(id=default_policy_id, created_at=datetime.utcnow())
    )


def downgrade() -> None:
    # Drop assistant column
    op.drop_column("assistants", "enable_memory")

    # Drop tables in reverse order
    op.drop_table("memory_consent_logs")
    op.drop_table("user_memory_consents")
    op.drop_table("agent_memories")
    op.drop_table("memory_retention_policies")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS consentactionenum")
    op.execute("DROP TYPE IF EXISTS memorytypeenum")
