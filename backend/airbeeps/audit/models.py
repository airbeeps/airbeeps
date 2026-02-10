"""
Audit log models for tracking admin operations.
"""

import uuid
from enum import Enum
from typing import Any

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Enum as SQLEnum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from airbeeps.models import Base


class AuditAction(str, Enum):
    """Types of auditable actions"""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_DELETE = "bulk_delete"
    EXPORT = "export"
    IMPORT = "import"
    LOGIN = "login"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    ROLE_CHANGE = "role_change"
    STATUS_CHANGE = "status_change"
    CONFIG_CHANGE = "config_change"


class AuditLog(Base):
    """
    Audit log entry for tracking administrative operations.

    Stores information about who did what, when, and to which entity.
    """

    __tablename__ = "audit_logs"

    # User who performed the action
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        nullable=True,
        index=True,
    )
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # Action details
    action: Mapped[AuditAction] = mapped_column(
        SQLEnum(AuditAction),
        nullable=False,
        index=True,
    )

    # Entity type (e.g., "assistant", "user", "knowledge_base")
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Entity ID (UUID as string for flexibility)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Entity name for display purposes
    entity_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Description of the action
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Before/after state for updates (JSON)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Request metadata
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Additional data (named extra_data because 'metadata' is reserved in SQLAlchemy)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action={self.action}, "
            f"entity_type={self.entity_type}, entity_id={self.entity_id})>"
        )
