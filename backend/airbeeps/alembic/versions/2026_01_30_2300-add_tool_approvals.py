"""Add tool approval system.

Revision ID: t00l_4ppr0v4l
Revises: cust_sp3c1al1st (add_custom_specialists)
Create Date: 2026-01-30 23:00:00.000000

Phase 3: Tool Approval Workflows
- Approval request tracking
- Approval policies
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import fastapi_users_db_sqlalchemy.generics


# revision identifiers, used by Alembic.
revision = "t00l_4ppr0v4l"
down_revision = "cust_sp3c1al1st"  # add_custom_specialists migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tool_approval_requests table
    op.create_table(
        "tool_approval_requests",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "user_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "requested_parameters",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "conversation_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "APPROVED", "REJECTED", "EXPIRED", name="approvalstatusenum"
            ),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "reviewed_by_id",
            fastapi_users_db_sqlalchemy.generics.GUID(),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When approval expires (null = no expiration)",
        ),
        sa.Column(
            "max_uses",
            sa.Integer(),
            nullable=True,
            comment="Maximum number of uses for this approval",
        ),
        sa.Column(
            "uses_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of times this approval has been used",
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
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tool_approval_requests_user_id", "tool_approval_requests", ["user_id"]
    )

    # Create tool_approval_policies table
    op.create_table(
        "tool_approval_policies",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "auto_approve_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "auto_approve_conditions",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("default_expiration_hours", sa.Integer(), nullable=True),
        sa.Column("default_max_uses", sa.Integer(), nullable=True),
        sa.Column(
            "notify_on_request",
            sa.Boolean(),
            nullable=False,
            server_default="true",
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
    )


def downgrade() -> None:
    op.drop_table("tool_approval_policies")
    op.drop_table("tool_approval_requests")
    op.execute("DROP TYPE IF EXISTS approvalstatusenum")
