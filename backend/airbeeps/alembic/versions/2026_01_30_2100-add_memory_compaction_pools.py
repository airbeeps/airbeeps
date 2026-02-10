"""Add memory compaction and shared pools.

Revision ID: ph4s3_m3m0ry
Revises: mult14g3nt5yx (add_multiagent_system)
Create Date: 2026-01-30 21:00:00.000000

Phase 3: Memory Compaction and Shared Pools
- Memory compaction tracking fields
- Shared memory pools
- Pool membership
- Pool memory associations
- Compaction logs
"""

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ph4s3_m3m0ry"
down_revision = "mult14g3nt5yx"  # add_multiagent_system migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add compaction tracking fields to agent_memories
    op.add_column(
        "agent_memories",
        sa.Column(
            "is_compacted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this memory was created from compaction",
        ),
    )
    op.add_column(
        "agent_memories",
        sa.Column(
            "parent_memory_ids",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="IDs of memories that were merged into this one",
        ),
    )
    op.add_column(
        "agent_memories",
        sa.Column(
            "compaction_date",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this memory was created via compaction",
        ),
    )
    op.add_column(
        "agent_memories",
        sa.Column(
            "original_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Number of original memories merged into this one",
        ),
    )

    # Create shared_memory_pools table
    op.create_table(
        "shared_memory_pools",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "pool_type",
            sa.Enum("TEAM", "ORGANIZATION", "PUBLIC", name="pooltypeenum"),
            nullable=False,
        ),
        sa.Column(
            "access_level",
            sa.Enum("READ_ONLY", "READ_WRITE", name="poolaccesslevelenum"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "assistant_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "max_memories",
            sa.Integer(),
            nullable=False,
            server_default="1000",
            comment="Maximum memories in this pool",
        ),
        sa.Column(
            "auto_share_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Auto-share new memories to this pool",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assistant_id"], ["assistants.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shared_memory_pools_owner_id", "shared_memory_pools", ["owner_id"]
    )

    # Create shared_pool_members table
    op.create_table(
        "shared_pool_members",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "pool_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "access_level",
            sa.Enum(
                "READ_ONLY", "READ_WRITE", name="poolaccesslevelenum", create_type=False
            ),
            nullable=True,
            comment="Override access level for this member",
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["pool_id"], ["shared_memory_pools.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shared_pool_members_pool_id", "shared_pool_members", ["pool_id"]
    )
    op.create_index(
        "ix_shared_pool_members_user_id", "shared_pool_members", ["user_id"]
    )
    op.create_index(
        "ix_shared_pool_members_pool_user",
        "shared_pool_members",
        ["pool_id", "user_id"],
        unique=True,
    )

    # Create shared_pool_memories table
    op.create_table(
        "shared_pool_memories",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "pool_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "memory_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "shared_by_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column(
            "shared_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["pool_id"], ["shared_memory_pools.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["memory_id"], ["agent_memories.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["shared_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shared_pool_memories_pool_id", "shared_pool_memories", ["pool_id"]
    )
    op.create_index(
        "ix_shared_pool_memories_memory_id", "shared_pool_memories", ["memory_id"]
    )
    op.create_index(
        "ix_shared_pool_memories_pool_memory",
        "shared_pool_memories",
        ["pool_id", "memory_id"],
        unique=True,
    )

    # Create memory_compaction_logs table
    op.create_table(
        "memory_compaction_logs",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "assistant_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column(
            "strategy",
            sa.Enum(
                "AGE",
                "SIMILARITY",
                "IMPORTANCE",
                "HYBRID",
                name="compactionstrategyenum",
            ),
            nullable=False,
        ),
        sa.Column("memories_before", sa.Integer(), nullable=False),
        sa.Column("memories_after", sa.Integer(), nullable=False),
        sa.Column("memories_merged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "memories_summarized", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "result_memory_ids",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "source_memory_ids",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assistant_id"], ["assistants.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_compaction_logs_user_id", "memory_compaction_logs", ["user_id"]
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("memory_compaction_logs")
    op.drop_table("shared_pool_memories")
    op.drop_table("shared_pool_members")
    op.drop_table("shared_memory_pools")

    # Drop columns from agent_memories
    op.drop_column("agent_memories", "original_count")
    op.drop_column("agent_memories", "compaction_date")
    op.drop_column("agent_memories", "parent_memory_ids")
    op.drop_column("agent_memories", "is_compacted")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS compactionstrategyenum")
    op.execute("DROP TYPE IF EXISTS poolaccesslevelenum")
    op.execute("DROP TYPE IF EXISTS pooltypeenum")
