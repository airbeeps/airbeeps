"""Add custom specialist types and routing rules.

Revision ID: cust_sp3c1al1st
Revises: ph4s3_m3m0ry (add_memory_compaction_pools)
Create Date: 2026-01-30 22:00:00.000000

Phase 3: Custom Specialist Types and Routing Rules
- Custom specialist type definitions
- Routing rules for specialist selection
- Performance metrics for analytics
"""

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "cust_sp3c1al1st"
down_revision = "ph4s3_m3m0ry"  # add_memory_compaction_pools migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create custom_specialist_types table
    op.create_table(
        "custom_specialist_types",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "tools",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "system_prompt_suffix",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "max_iterations",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "cost_limit_usd",
            sa.Float(),
            nullable=False,
            server_default="0.25",
        ),
        sa.Column(
            "can_handoff_to",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "priority_keywords",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_by_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
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
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create specialist_routing_rules table
    op.create_table(
        "specialist_routing_rules",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("specialist_name", sa.String(50), nullable=False, index=True),
        sa.Column(
            "custom_specialist_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column(
            "rule_type",
            sa.Enum("KEYWORD", "REGEX", "LLM", name="routingruletypeenum"),
            nullable=False,
        ),
        sa.Column("rule_value", sa.Text(), nullable=False),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("description", sa.Text(), nullable=True),
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
            ["custom_specialist_id"],
            ["custom_specialist_types.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create specialist_performance_metrics table
    op.create_table(
        "specialist_performance_metrics",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("specialist_name", sa.String(50), nullable=False, index=True),
        sa.Column(
            "period_date", sa.DateTime(timezone=True), nullable=False, index=True
        ),
        sa.Column(
            "total_invocations", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "successful_invocations", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "failed_invocations", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_handoffs_from", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_handoffs_to", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_iterations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "total_duration_ms", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "tool_usage",
            sa.JSON(),
            nullable=False,
            server_default="{}",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "specialist_name", "period_date", name="uq_specialist_period"
        ),
    )


def downgrade() -> None:
    op.drop_table("specialist_performance_metrics")
    op.drop_table("specialist_routing_rules")
    op.drop_table("custom_specialist_types")
    op.execute("DROP TYPE IF EXISTS routingruletypeenum")
