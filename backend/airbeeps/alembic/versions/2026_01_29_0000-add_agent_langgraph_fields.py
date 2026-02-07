"""Add LangGraph agent fields to assistants

Revision ID: k3l4m5n6o7p8
Revises: f7g8h9i0j1k2
Create Date: 2026-01-29 00:00:00.000000

"""

from collections.abc import Sequence

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k3l4m5n6o7p8"
down_revision: str | None = "f7g8h9i0j1k2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add agent planning and reflection fields
    op.add_column(
        "assistants",
        sa.Column(
            "agent_enable_planning",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Enable LLM-based task planning",
        ),
    )
    op.add_column(
        "assistants",
        sa.Column(
            "agent_enable_reflection",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Enable quality reflection after tool use",
        ),
    )
    op.add_column(
        "assistants",
        sa.Column(
            "agent_reflection_threshold",
            sa.Float(),
            nullable=False,
            server_default="7.0",
            comment="Quality threshold (0-10) for reflection pass",
        ),
    )

    # Add budget control fields
    op.add_column(
        "assistants",
        sa.Column(
            "agent_token_budget",
            sa.Integer(),
            nullable=False,
            server_default="8000",
            comment="Maximum tokens per conversation turn",
        ),
    )
    op.add_column(
        "assistants",
        sa.Column(
            "agent_max_tool_calls",
            sa.Integer(),
            nullable=False,
            server_default="20",
            comment="Maximum tool calls per conversation",
        ),
    )
    op.add_column(
        "assistants",
        sa.Column(
            "agent_cost_limit_usd",
            sa.Float(),
            nullable=False,
            server_default="0.50",
            comment="Maximum cost per conversation in USD",
        ),
    )
    op.add_column(
        "assistants",
        sa.Column(
            "agent_max_parallel_tools",
            sa.Integer(),
            nullable=False,
            server_default="3",
            comment="Maximum concurrent tool calls",
        ),
    )

    # Create tool_permissions table for role-based access control
    op.create_table(
        "tool_permissions",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column(
            "security_level", sa.String(20), nullable=False, server_default="moderate"
        ),
        sa.Column("allowed_roles", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "max_calls_per_hour", sa.Integer(), nullable=False, server_default="100"
        ),
        sa.Column(
            "max_calls_per_day", sa.Integer(), nullable=False, server_default="1000"
        ),
        sa.Column(
            "requires_approval", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("cost_per_call", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tool_permissions_tool_name", "tool_permissions", ["tool_name"], unique=True
    )

    # Create tool_usage_logs table for audit
    op.create_table(
        "tool_usage_logs",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "user_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False
        ),
        sa.Column(
            "assistant_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=True
        ),
        sa.Column(
            "conversation_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_input", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("tool_output", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assistant_id"], ["assistants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_usage_logs_user_id", "tool_usage_logs", ["user_id"])
    op.create_index("ix_tool_usage_logs_tool_name", "tool_usage_logs", ["tool_name"])
    op.create_index("ix_tool_usage_logs_created_at", "tool_usage_logs", ["created_at"])

    # Create langgraph_checkpoints table for state persistence
    op.create_table(
        "langgraph_checkpoints",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("checkpoint_id", sa.String(255), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(255), nullable=True),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_langgraph_checkpoints_thread_checkpoint",
        "langgraph_checkpoints",
        ["thread_id", "checkpoint_id"],
        unique=True,
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("langgraph_checkpoints")
    op.drop_table("tool_usage_logs")
    op.drop_table("tool_permissions")

    # Drop columns
    op.drop_column("assistants", "agent_max_parallel_tools")
    op.drop_column("assistants", "agent_cost_limit_usd")
    op.drop_column("assistants", "agent_max_tool_calls")
    op.drop_column("assistants", "agent_token_budget")
    op.drop_column("assistants", "agent_reflection_threshold")
    op.drop_column("assistants", "agent_enable_reflection")
    op.drop_column("assistants", "agent_enable_planning")
