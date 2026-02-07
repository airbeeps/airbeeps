"""Add agentic RAG fields to assistants table.

Revision ID: 20260130_1500
Revises: 2026_01_30_1000 (add_agent_traces)
Create Date: 2026-01-30 15:00:00.000000

Phase 5: Agentic RAG + Parallel Execution
- Query planning, self-RAG, multi-hop retrieval configuration
- Enhanced parallel execution settings
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4g3nt1cr4g5x"
down_revision = "tr4c35t0r4g3x"  # add_agent_traces migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add agentic RAG and parallel execution fields to assistants table."""

    # Add agentic RAG mode fields
    op.add_column(
        "assistants",
        sa.Column(
            "agent_rag_mode",
            sa.String(50),
            server_default="standard",
            nullable=False,
            comment="Agentic RAG mode: standard, query_planning, self_rag, multi_hop",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "agent_enable_query_planning",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Enable query decomposition for complex queries",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "agent_enable_self_rag",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Enable self-critique and retry for retrieval",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "agent_enable_multi_hop",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Enable multi-hop retrieval for complex reasoning",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "agent_self_rag_min_confidence",
            sa.Integer(),
            server_default="50",
            nullable=False,
            comment="Minimum confidence score (0-100) for self-RAG to accept results",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "agent_multi_hop_max_hops",
            sa.Integer(),
            server_default="3",
            nullable=False,
            comment="Maximum number of retrieval hops for multi-hop mode",
        ),
    )

    # Add enhanced parallel execution fields
    op.add_column(
        "assistants",
        sa.Column(
            "agent_tool_timeout_seconds",
            sa.Integer(),
            server_default="30",
            nullable=False,
            comment="Default timeout for tool execution in seconds",
        ),
    )

    op.add_column(
        "assistants",
        sa.Column(
            "agent_tool_max_retries",
            sa.Integer(),
            server_default="2",
            nullable=False,
            comment="Maximum retries for failed tool calls",
        ),
    )


def downgrade() -> None:
    """Remove agentic RAG and parallel execution fields from assistants table."""

    # Remove parallel execution fields
    op.drop_column("assistants", "agent_tool_max_retries")
    op.drop_column("assistants", "agent_tool_timeout_seconds")

    # Remove agentic RAG fields
    op.drop_column("assistants", "agent_multi_hop_max_hops")
    op.drop_column("assistants", "agent_self_rag_min_confidence")
    op.drop_column("assistants", "agent_enable_multi_hop")
    op.drop_column("assistants", "agent_enable_self_rag")
    op.drop_column("assistants", "agent_enable_query_planning")
    op.drop_column("assistants", "agent_rag_mode")
