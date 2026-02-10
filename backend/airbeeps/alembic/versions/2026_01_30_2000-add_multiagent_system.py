"""Add multi-agent system tables and fields.

Revision ID: 20260130_2000
Revises: 20260130_1500 (add_agentic_rag_fields)
Create Date: 2026-01-30 20:00:00.000000

Phase 6: Multi-Agent System
- Specialist agent types
- Collaboration configuration
- Agent collaboration logs
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "mult14g3nt5yx"
down_revision = "a4g3nt1cr4g5x"  # add_agentic_rag_fields migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add multi-agent system fields and tables."""

    # Add specialist type field to assistants
    op.add_column(
        "assistants",
        sa.Column(
            "specialist_type",
            sa.String(50),
            nullable=True,
            comment="Specialist type: RESEARCH, CODE, DATA, GENERAL",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "can_collaborate",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Whether this assistant can participate in multi-agent collaboration",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "collaboration_max_handoffs",
            sa.Integer(),
            server_default="3",
            nullable=False,
            comment="Maximum handoffs allowed during collaboration",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "collaboration_cost_limit_per_handoff",
            sa.Float(),
            server_default="0.25",
            nullable=False,
            comment="Cost limit per handoff in USD",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "collaboration_allowed_specialists",
            sa.JSON(),
            server_default="[]",
            nullable=False,
            comment="List of specialist types this assistant can collaborate with",
        ),
    )

    # Create agent collaboration logs table
    op.create_table(
        "agent_collaboration_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "conversation_id",
            sa.UUID(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "initial_assistant_id",
            sa.UUID(),
            sa.ForeignKey("assistants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("final_output", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "RUNNING",
                "COMPLETED",
                "FAILED",
                "LOOP_DETECTED",
                "BUDGET_EXCEEDED",
                name="collaborationstatusenum",
            ),
            server_default="RUNNING",
            nullable=False,
        ),
        sa.Column("agent_chain", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("steps", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("total_iterations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_cost_usd", sa.Float(), server_default="0.0", nullable=False),
        sa.Column(
            "total_duration_ms", sa.Float(), server_default="0.0", nullable=False
        ),
        sa.Column("handoff_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(50), nullable=True),
        sa.Column("extra_data", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for common queries
    op.create_index(
        "ix_agent_collaboration_logs_user_time",
        "agent_collaboration_logs",
        ["user_id", "created_at"],
    )

    op.create_index(
        "ix_agent_collaboration_logs_conversation",
        "agent_collaboration_logs",
        ["conversation_id"],
    )

    op.create_index(
        "ix_agent_collaboration_logs_status",
        "agent_collaboration_logs",
        ["status"],
    )

    op.create_index(
        "ix_agent_collaboration_logs_assistant",
        "agent_collaboration_logs",
        ["initial_assistant_id"],
    )


def downgrade() -> None:
    """Remove multi-agent system fields and tables."""

    # Drop indexes
    op.drop_index(
        "ix_agent_collaboration_logs_assistant",
        table_name="agent_collaboration_logs",
    )
    op.drop_index(
        "ix_agent_collaboration_logs_status",
        table_name="agent_collaboration_logs",
    )
    op.drop_index(
        "ix_agent_collaboration_logs_conversation",
        table_name="agent_collaboration_logs",
    )
    op.drop_index(
        "ix_agent_collaboration_logs_user_time",
        table_name="agent_collaboration_logs",
    )

    # Drop collaboration logs table
    op.drop_table("agent_collaboration_logs")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS collaborationstatusenum")

    # Remove assistant columns
    op.drop_column("assistants", "collaboration_allowed_specialists")
    op.drop_column("assistants", "collaboration_cost_limit_per_handoff")
    op.drop_column("assistants", "collaboration_max_handoffs")
    op.drop_column("assistants", "can_collaborate")
    op.drop_column("assistants", "specialist_type")
