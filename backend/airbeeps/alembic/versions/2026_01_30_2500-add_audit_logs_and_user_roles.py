"""Add audit logs and user roles.

Revision ID: 4ud1t_l0g5_r0l35
Revises: m0d3l_4n4lyt1c5 (add_model_analytics)
Create Date: 2026-01-30 25:00:00.000000

Phase 5: Audit Logging and Role Management
- Audit logs table for tracking admin operations
- User role field for RBAC foundation
"""

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4ud1t_l0g5_r0l35"
down_revision = "m0d3l_4n4lyt1c5"  # add_model_analytics migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # For PostgreSQL, create enums
    if not is_sqlite:
        audit_action_enum = postgresql.ENUM(
            "create",
            "update",
            "delete",
            "bulk_delete",
            "export",
            "import",
            "login",
            "logout",
            "password_change",
            "role_change",
            "status_change",
            "config_change",
            name="auditaction",
            create_type=True,
        )
        audit_action_enum.create(bind, checkfirst=True)

        user_role_enum = postgresql.ENUM(
            "admin",
            "editor",
            "viewer",
            name="userrole",
            create_type=True,
        )
        user_role_enum.create(bind, checkfirst=True)

    # Choose column types based on dialect
    if is_sqlite:
        action_type = sa.String(50)
        json_type = sa.JSON()
        role_type = sa.String(20)
        created_default = sa.text("(datetime('now'))")
    else:
        action_type = postgresql.ENUM(
            "create",
            "update",
            "delete",
            "bulk_delete",
            "export",
            "import",
            "login",
            "logout",
            "password_change",
            "role_change",
            "status_change",
            "config_change",
            name="auditaction",
            create_type=False,
        )
        json_type = postgresql.JSONB()
        role_type = postgresql.ENUM(
            "admin", "editor", "viewer", name="userrole", create_type=False
        )
        created_default = sa.text("now()")

    # Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column(
            "user_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=True
        ),
        sa.Column("user_email", sa.String(320), nullable=True),
        sa.Column("action", action_type, nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("entity_name", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("changes", json_type, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("extra_data", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=created_default,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=created_default,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for common queries
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # Composite index for common filter combination
    op.create_index(
        "ix_audit_logs_entity_type_created_at",
        "audit_logs",
        ["entity_type", "created_at"],
    )

    # Add role column to users table
    op.add_column(
        "users",
        sa.Column(
            "role",
            role_type,
            nullable=True,
            server_default="viewer",
        ),
    )
    op.create_index("ix_users_role", "users", ["role"])


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Remove role column from users
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "role")

    # Drop audit_logs table
    op.drop_index("ix_audit_logs_entity_type_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    # Drop enums (PostgreSQL only)
    if not is_sqlite:
        op.execute("DROP TYPE IF EXISTS auditaction")
        op.execute("DROP TYPE IF EXISTS userrole")
