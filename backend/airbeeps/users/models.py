from datetime import datetime
from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseUserTableUUID,
)
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airbeeps.models import Base

if TYPE_CHECKING:
    from airbeeps.auth.refresh_token_models import RefreshToken


class User(Base, SQLAlchemyBaseUserTableUUID):
    __tablename__ = "users"

    # Override base class email field, set to nullable
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True)

    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # User language preference (currently English only)
    language: Mapped[str | None] = mapped_column(
        String(10), nullable=True, default="en"
    )

    # Email sending rate limit timestamp
    last_verification_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_password_reset_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Account lockout fields for brute force protection
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Refresh Token relationship
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
