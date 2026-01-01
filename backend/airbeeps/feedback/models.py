import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum as SQLEnum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airbeeps.models import Base

if TYPE_CHECKING:
    from airbeeps.assistants.models import Assistant, Conversation, Message
    from airbeeps.users.models import User


class MessageFeedbackRatingEnum(enum.Enum):
    """Thumbs-up/down feedback rating."""

    UP = "UP"
    DOWN = "DOWN"


class MessageFeedback(Base):
    """Feedback left by a user for a specific assistant message."""

    __tablename__ = "message_feedbacks"

    # Enforce one feedback per user per message (allows update/re-submit).
    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", name="uq_message_feedback_message_user"
        ),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assistant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    rating: Mapped[MessageFeedbackRatingEnum] = mapped_column(
        SQLEnum(MessageFeedbackRatingEnum), nullable=False
    )

    reasons: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default="[]",
        comment="User-selected reason tags (UI quick options)",
    )
    comment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional free-text feedback"
    )
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Optional structured metadata for analytics",
    )

    # Relationships (not required for writes, but useful for admin/analytics later).
    message: Mapped["Message"] = relationship("Message")
    conversation: Mapped["Conversation"] = relationship("Conversation")
    assistant: Mapped["Assistant"] = relationship("Assistant")
    user: Mapped["User"] = relationship("User")
