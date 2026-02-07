"""Add model analytics and A/B testing.

Revision ID: m0d3l_4n4lyt1c5
Revises: t00l_4ppr0v4l (add_tool_approvals)
Create Date: 2026-01-30 24:00:00.000000

Phase 3: Model Analytics and A/B Testing
- A/B experiments
- Experiment assignments
- Model usage metrics
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import fastapi_users_db_sqlalchemy.generics


# revision identifiers, used by Alembic.
revision = "m0d3l_4n4lyt1c5"
down_revision = "t00l_4ppr0v4l"  # add_tool_approvals migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create model_experiments table
    op.create_table(
        "model_experiments",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "ACTIVE", "PAUSED", "COMPLETED", name="experimentstatusenum"
            ),
            nullable=False,
        ),
        sa.Column(
            "model_a_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "model_b_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "traffic_split_percent",
            sa.Integer(),
            nullable=False,
            server_default="50",
            comment="Percentage of traffic to variant A (0-100)",
        ),
        sa.Column(
            "assistant_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "min_sample_size",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
        sa.Column(
            "config",
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
        sa.ForeignKeyConstraint(["model_a_id"], ["models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_b_id"], ["models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assistant_id"], ["assistants.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create experiment_assignments table
    op.create_table(
        "experiment_assignments",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "experiment_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column(
            "variant",
            sa.String(1),
            nullable=False,
            comment="A or B",
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
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
            ["experiment_id"], ["model_experiments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "experiment_id", "user_id", name="uq_experiment_user_assignment"
        ),
    )
    op.create_index(
        "ix_experiment_assignments_experiment_id",
        "experiment_assignments",
        ["experiment_id"],
    )
    op.create_index(
        "ix_experiment_assignments_user_id", "experiment_assignments", ["user_id"]
    )

    # Create model_usage_metrics table
    op.create_table(
        "model_usage_metrics",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "model_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column("metric_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "successful_requests", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("failed_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "total_prompt_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_completion_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("min_latency_ms", sa.Float(), nullable=True),
        sa.Column("max_latency_ms", sa.Float(), nullable=True),
        sa.Column("p95_latency_ms", sa.Float(), nullable=True),
        sa.Column(
            "total_feedback_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "positive_feedback_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "negative_feedback_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("unique_users", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "metric_date", name="uq_model_usage_metric"),
    )
    op.create_index(
        "ix_model_usage_metrics_model_id", "model_usage_metrics", ["model_id"]
    )
    op.create_index(
        "ix_model_usage_metrics_metric_date", "model_usage_metrics", ["metric_date"]
    )


def downgrade() -> None:
    op.drop_table("model_usage_metrics")
    op.drop_table("experiment_assignments")
    op.drop_table("model_experiments")
    op.execute("DROP TYPE IF EXISTS experimentstatusenum")
