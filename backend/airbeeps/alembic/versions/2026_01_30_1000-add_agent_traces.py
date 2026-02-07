"""Add agent traces table for observability

Revision ID: tr4c35t0r4g3
Revises: m3m0ry5y5t3m
Create Date: 2026-01-30 10:00:00.000000

"""

from collections.abc import Sequence

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "tr4c35t0r4g3x"
down_revision: str | None = "m3m0ry5y5t3m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create agent_traces table
    op.create_table(
        "agent_traces",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        # Trace context (OpenTelemetry IDs)
        sa.Column(
            "trace_id",
            sa.String(64),
            nullable=False,
            index=True,
            comment="OpenTelemetry trace ID",
        ),
        sa.Column(
            "span_id",
            sa.String(32),
            nullable=False,
            index=True,
            comment="OpenTelemetry span ID",
        ),
        sa.Column(
            "parent_span_id",
            sa.String(32),
            nullable=True,
            comment="Parent span ID for nested spans",
        ),
        # Span info
        sa.Column(
            "span_name",
            sa.String(200),
            nullable=False,
            index=True,
            comment="Name of the span (e.g., agent_execution, tool_web_search)",
        ),
        sa.Column(
            "span_kind",
            sa.String(50),
            nullable=False,
            server_default="INTERNAL",
            comment="Span kind: INTERNAL, CLIENT, SERVER, PRODUCER, CONSUMER",
        ),
        # Context references
        sa.Column(
            "conversation_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "message_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "assistant_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            sa.ForeignKey("assistants.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        # Timing
        sa.Column(
            "start_time",
            sa.DateTime(),
            nullable=False,
            index=True,
            comment="Span start time",
        ),
        sa.Column(
            "end_time",
            sa.DateTime(),
            nullable=False,
            comment="Span end time",
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=False,
            comment="Latency in milliseconds",
        ),
        # Data (JSON for flexibility, already PII-redacted)
        sa.Column(
            "attributes",
            sa.JSON(),
            nullable=True,
            comment="Span attributes (already PII-redacted)",
        ),
        sa.Column(
            "events",
            sa.JSON(),
            nullable=True,
            comment="Span events/logs",
        ),
        # Metrics
        sa.Column(
            "tokens_used",
            sa.Integer(),
            nullable=True,
            comment="Tokens used in this span",
        ),
        sa.Column(
            "cost_usd",
            sa.Float(),
            nullable=True,
            comment="Cost in USD",
        ),
        # Status
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="Whether the operation succeeded",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if failed",
        ),
        sa.Column(
            "status_code",
            sa.String(20),
            nullable=False,
            server_default="OK",
            comment="OpenTelemetry status: OK, ERROR, UNSET",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create composite indexes for common queries
    op.create_index(
        "ix_agent_traces_trace_time",
        "agent_traces",
        ["trace_id", "start_time"],
    )
    op.create_index(
        "ix_agent_traces_user_time",
        "agent_traces",
        ["user_id", "start_time"],
    )
    op.create_index(
        "ix_agent_traces_assistant_time",
        "agent_traces",
        ["assistant_id", "start_time"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_agent_traces_assistant_time", table_name="agent_traces")
    op.drop_index("ix_agent_traces_user_time", table_name="agent_traces")
    op.drop_index("ix_agent_traces_trace_time", table_name="agent_traces")

    # Drop table
    op.drop_table("agent_traces")
